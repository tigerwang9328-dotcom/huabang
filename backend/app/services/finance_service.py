"""
财务中心 - Service 层（核心业务逻辑）
========================================
所有��务口径计算��中在此，不在 API 层写 SQL。
数据来源：
  - dm_store_daily      → 销售/退款/成本/利润
  - biz_finance_fees    → 费用明细（按 fee_type 分类）
  - biz_finance_receipts → 回款
  - fin_cost_config     → 月度固定费用
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_, case


# ── 工具函数 ──

def _month_range(month_str: str) -> tuple[date, date]:
    """'YYYY-MM' → (月初, 下月初)"""
    y, m = int(month_str[:4]), int(month_str[5:7])
    begin = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    return begin, end


def _d(val) -> float:
    """Decimal/None → float"""
    if val is None:
        return 0.0
    return float(val)


# ══════════════════════════════════════════════════════════════
# 1. 财务总览 KPI（11项指标）
# ══════════════════════════════════════════════════════════════

async def get_overview(db: AsyncSession, month: str) -> dict:
    """
    月度财务总览，汇总11项KPI指标���
    口径：
      - 销售额/退款/成本 → dm_store_daily
      - 费用 → biz_finance_fees (按 fee_type 分组)
      - 回款 → biz_finance_receipts
      - 人工 → fin_cost_config (月度÷天数)
    """
    begin, end = _month_range(month)

    # 从 dm_store_daily 聚合销售���据
    sales_q = text("""
        SELECT
            COALESCE(SUM(sale_amount), 0)       AS total_sales,
            COALESCE(SUM(refund_amount), 0)     AS total_refund,
            COALESCE(SUM(sale_cogs), 0)         AS total_cogs,
            COALESCE(SUM(refund_cogs), 0)       AS total_refund_cogs,
            COALESCE(SUM(operating_profit), 0)  AS total_op_profit,
            COUNT(DISTINCT store_id)             AS store_count
        FROM dm_store_daily
        WHERE biz_date >= :begin AND biz_date < :end
    """)
    sr = await db.execute(sales_q, {"begin": begin, "end": end})
    s = sr.mappings().first()

    total_sales       = _d(s["total_sales"])
    total_refund      = _d(s["total_refund"])
    total_cogs        = _d(s["total_cogs"])
    total_refund_cogs = _d(s["total_refund_cogs"])
    store_count       = int(s["store_count"])

    # 费用��类型汇总
    fee_q = text("""
        SELECT fee_type, COALESCE(SUM(amount), 0) AS total
        FROM biz_finance_fees
        WHERE fee_date >= :begin AND fee_date < :end
        GROUP BY fee_type
    """)
    fr = await db.execute(fee_q, {"begin": begin, "end": end})
    fee_map = {row["fee_type"]: _d(row["total"]) for row in fr.mappings()}

    total_ad        = fee_map.get("ad", 0)
    total_logistics = fee_map.get("logistics", 0)
    total_pack      = fee_map.get("packing", 0)
    total_commission = fee_map.get("commission", 0)

    # 月度人工��本（从 fin_cost_config 读取，日摊到当月）
    labor_q = text("""
        SELECT COALESCE(SUM(amount), 0) AS labor
        FROM fin_cost_config
        WHERE month = :month AND cost_type = 'labor'
    """)
    lr = await db.execute(labor_q, {"month": month})
    total_labor = _d(lr.scalar())

    # 回款
    receipt_q = text("""
        SELECT COALESCE(SUM(amount), 0) AS total_receipt
        FROM biz_finance_receipts
        WHERE receipt_date >= :begin AND receipt_date < :end
    """)
    rr = await db.execute(receipt_q, {"begin": begin, "end": end})
    total_receipt = _d(rr.scalar())

    # 利润计算
    # 毛利 = 销��额 - 销售成本 - (退款��� - 退货成本)
    gross_profit = total_sales - total_cogs - (total_refund - total_refund_cogs)
    # 净利 = 毛利 - 广告 - 物流 - 包材 - 佣金 - 人工
    all_expense = total_ad + total_logistics + total_pack + total_commission + total_labor
    net_profit = gross_profit - all_expense
    # 净利率 = 净利 / 销售额
    profit_rate = (net_profit / total_sales * 100) if total_sales > 0 else 0
    # 现金流净额 = 回款 - 当月所有费用支出
    total_fee_sum = sum(fee_map.values())
    cashflow_net = total_receipt - total_fee_sum

    return {
        "period":           month,
        "total_sales":      round(total_sales, 2),
        "total_receipt":    round(total_receipt, 2),
        "total_refund":     round(total_refund, 2),
        "total_settlement": round(total_receipt, 2),   # 平台结算 ≈ 回款
        "total_ad_cost":    round(total_ad, 2),
        "total_logistics":  round(total_logistics, 2),
        "total_pack_cost":  round(total_pack, 2),
        "total_labor_cost": round(total_labor, 2),
        "gross_profit":     round(gross_profit, 2),
        "net_profit":       round(net_profit, 2),
        "cashflow_net":     round(cashflow_net, 2),
        "profit_rate":      round(profit_rate, 2),
        "store_count":      store_count,
    }


# ══════════════════════════════════════════════════════════════
# 2. 趋势数���（近N个月��
# ══════════════════════════════════════════════════════════════

async def get_trend(db: AsyncSession, month: str, months: int = 6) -> list[dict]:
    """近N个月销售/费用/利润趋势"""
    y, m = int(month[:4]), int(month[5:7])
    result = []

    for i in range(months - 1, -1, -1):
        tm = m - i
        ty = y
        while tm <= 0:
            tm += 12
            ty -= 1
        period = f"{ty}-{tm:02d}"
        begin, end = _month_range(period)

        sr = await db.execute(text("""
            SELECT COALESCE(SUM(sale_amount),0) AS sales,
                   COALESCE(SUM(sale_cogs),0)   AS cogs,
                   COALESCE(SUM(operating_profit),0) AS profit
            FROM dm_store_daily
            WHERE biz_date >= :b AND biz_date < :e
        """), {"b": begin, "e": end})
        s = sr.mappings().first()

        cr = await db.execute(text("""
            SELECT COALESCE(SUM(amount),0) AS cost
            FROM biz_finance_fees
            WHERE fee_date >= :b AND fee_date < :e
        """), {"b": begin, "e": end})

        result.append({
            "period": f"{tm}月",
            "sales":  round(_d(s["sales"]), 2),
            "cost":   round(_d(cr.scalar()), 2),
            "profit": round(_d(s["profit"]), 2),
        })

    return result


# ══════════════════════════════════════════════════════════════
# 3. 店铺利润排行
# ══════════════════════════════════════════════════════════════

async def get_store_ranking(
    db: AsyncSession, month: str,
    platform_id: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """
    按月汇总各店铺利润，排名按利润降序。
    口径：毛利 = sale_amount - sale_cogs - (refund_amount - refund_cogs)
    """
    begin, end = _month_range(month)

    sql = """
        SELECT
            d.store_id,
            s.store_name,
            COALESCE(p.name, '') AS platform,
            COALESCE(SUM(d.sale_amount), 0)   AS sales,
            COALESCE(SUM(d.refund_amount), 0) AS refund,
            COALESCE(SUM(d.sale_cogs), 0)     AS cogs,
            COALESCE(SUM(d.ad_cost), 0)       AS ad_cost,
            COALESCE(SUM(d.operating_profit), 0) AS gross_profit
        FROM dm_store_daily d
        JOIN biz_stores s ON s.id = d.store_id
        LEFT JOIN biz_platforms p ON p.id = s.platform_id
        WHERE d.biz_date >= :begin AND d.biz_date < :end
    """
    params = {"begin": begin, "end": end}

    if platform_id:
        sql += " AND s.platform_id = :pid"
        params["pid"] = platform_id

    sql += """
        GROUP BY d.store_id, s.store_name, p.name
        ORDER BY gross_profit DESC
        LIMIT :limit
    """
    params["limit"] = limit

    r = await db.execute(text(sql), params)
    rows = []
    for row in r.mappings():
        sales = _d(row["sales"])
        gp = _d(row["gross_profit"])
        rows.append({
            "store_id":     row["store_id"],
            "store_name":   row["store_name"],
            "platform":     row["platform"],
            "sales":        round(sales, 2),
            "refund":       round(_d(row["refund"]), 2),
            "cogs":         round(_d(row["cogs"]), 2),
            "ad_cost":      round(_d(row["ad_cost"]), 2),
            "gross_profit": round(gp, 2),
            "profit_rate":  round(gp / sales * 100, 2) if sales > 0 else 0,
        })
    return rows


# ══════════════════════════════════════════════════════════════
# 4. 现金流日报
# ══════════════════════════════════════════════════════════════

async def get_cashflow_daily(
    db: AsyncSession, begin: date, end: date,
) -> list[dict]:
    """逐日现金流：回款 - 支出（逐日遍历，兼容asyncpg）"""
    result = []
    current = end - timedelta(days=1)
    while current >= begin:
        d = current
        rr = await db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM biz_finance_receipts WHERE receipt_date = :d"
        ), {"d": d})
        receipt = _d(rr.scalar())
        er = await db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM biz_finance_fees WHERE fee_date = :d"
        ), {"d": d})
        expense = _d(er.scalar())
        sr = await db.execute(text(
            "SELECT COUNT(DISTINCT store_id) FROM dm_store_daily WHERE biz_date = :d"
        ), {"d": d})
        sc = int(sr.scalar() or 0)
        result.append({
            "biz_date":      str(d),
            "total_receipt":  round(receipt, 2),
            "total_expense":  round(expense, 2),
            "cashflow_net":   round(receipt - expense, 2),
            "store_count":    sc,
        })
        current -= timedelta(days=1)
    return result


# ══════════════════════════════════════════════════════════════
# 5. 财务明细（分页）
# ══════════════════════════════════════════════════════════════

async def get_details(
    db: AsyncSession, month: str,
    store_id: Optional[int] = None,
    page: int = 1, page_size: int = 30,
) -> dict:
    """按日+店铺的财务明细表"""
    begin, end = _month_range(month)
    where = "WHERE d.biz_date >= :begin AND d.biz_date < :end"
    params: dict = {"begin": begin, "end": end}

    if store_id:
        where += " AND d.store_id = :sid"
        params["sid"] = store_id

    # 总数
    cnt_r = await db.execute(text(f"""
        SELECT COUNT(*) FROM dm_store_daily d {where}
    """), params)
    total = cnt_r.scalar() or 0

    # 分页数据
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    data_r = await db.execute(text(f"""
        SELECT d.biz_date, d.store_id, s.store_name,
               d.sale_amount, d.refund_amount, d.sale_cogs,
               d.refund_cogs, d.ad_cost, d.operating_profit,
               d.order_count, d.shipped_qty
        FROM dm_store_daily d
        JOIN biz_stores s ON s.id = d.store_id
        {where}
        ORDER BY d.biz_date DESC, d.store_id
        LIMIT :limit OFFSET :offset
    """), params)

    rows = []
    for r in data_r.mappings():
        rows.append({
            "biz_date":    str(r["biz_date"]),
            "store_id":    r["store_id"],
            "store_name":  r["store_name"],
            "sales":       round(_d(r["sale_amount"]), 2),
            "refund":      round(_d(r["refund_amount"]), 2),
            "cogs":        round(_d(r["sale_cogs"]), 2),
            "ad_cost":     round(_d(r["ad_cost"]), 2),
            "profit":      round(_d(r["operating_profit"]), 2),
            "orders":      r["order_count"] or 0,
            "qty":         r["shipped_qty"] or 0,
        })

    return {"total": total, "page": page, "page_size": page_size, "rows": rows}


# ══════════════════════════════════════════════════════════════
# 6. 风险预警
# ══════════════════════════════════════════════════════════════

async def get_risk_alerts(
    db: AsyncSession, unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """获取财务风险预警列表"""
    sql = "SELECT * FROM fin_risk_alerts"
    if unread_only:
        sql += " WHERE is_read = false"
    sql += " ORDER BY biz_date DESC, id DESC LIMIT :limit"

    r = await db.execute(text(sql), {"limit": limit})
    return [
        {
            "id":           row["id"],
            "biz_date":     str(row["biz_date"]),
            "alert_type":   row["alert_type"],
            "alert_level":  row["alert_level"],
            "store_name":   row["store_name"] or "",
            "metric_name":  row["metric_name"] or "",
            "threshold":    _d(row["threshold"]),
            "actual_value": _d(row["actual_value"]),
            "message":      row["message"] or "",
            "is_read":      row["is_read"],
        }
        for row in r.mappings()
    ]


async def mark_alert_read(db: AsyncSession, alert_id: int, user_id: int):
    """标记预警已读"""
    await db.execute(text("""
        UPDATE fin_risk_alerts SET is_read = true, read_by = :uid, updated_at = NOW()
        WHERE id = :aid
    """), {"aid": alert_id, "uid": user_id})
    await db.commit()
