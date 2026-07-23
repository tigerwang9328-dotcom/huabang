"""
财务中心 - 定时任务服务
========================================
1. aggregate_daily_summary  每日聚合 fin_daily_summary
2. scan_finance_risks       扫描财务风险生成预警
"""
import logging
from datetime import date, timedelta
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def aggregate_daily_summary(target_date: date = None):
    """
    聚合指定日期的财务日汇总到 fin_daily_summary。
    口径：
      - 销售/退款/成本 → dm_store_daily
      - 费用 → biz_finance_fees（按 fee_type 分组）
      - 回款 → biz_finance_receipts
      - 人工 → fin_cost_config（月度÷当月天数日摊）
    默认聚合昨天的数据。
    """
    if not target_date:
        target_date = date.today() - timedelta(days=1)

    month_str = f"{target_date.year}-{target_date.month:02d}"
    # 当月天数
    import calendar
    days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]

    async with AsyncSessionLocal() as db:
        try:
            # 销售数据
            sr = await db.execute(text("""
                SELECT
                    COALESCE(SUM(sale_amount), 0)   AS total_sales,
                    COALESCE(SUM(refund_amount), 0) AS total_refund,
                    COALESCE(SUM(sale_cogs), 0)     AS total_cogs,
                    COALESCE(SUM(refund_cogs), 0)   AS total_refund_cogs,
                    COUNT(DISTINCT store_id)         AS store_count
                FROM dm_store_daily WHERE biz_date = :d
            """), {"d": target_date})
            s = sr.mappings().first()

            total_sales       = float(s["total_sales"])
            total_refund      = float(s["total_refund"])
            total_cogs        = float(s["total_cogs"])
            total_refund_cogs = float(s["total_refund_cogs"])
            store_count       = int(s["store_count"])

            # 费用分类
            fr = await db.execute(text("""
                SELECT fee_type, COALESCE(SUM(amount), 0) AS total
                FROM biz_finance_fees WHERE fee_date = :d GROUP BY fee_type
            """), {"d": target_date})
            fee_map = {row["fee_type"]: float(row["total"]) for row in fr.mappings()}

            total_ad       = fee_map.get("ad", 0)
            total_logistics = fee_map.get("logistics", 0)
            total_pack     = fee_map.get("packing", 0)
            total_commission = fee_map.get("commission", 0)

            # 人工日摊
            lr = await db.execute(text("""
                SELECT COALESCE(SUM(amount), 0) / :days AS daily_labor
                FROM fin_cost_config WHERE month = :m AND cost_type = 'labor'
            """), {"m": month_str, "days": days_in_month})
            total_labor = float(lr.scalar() or 0)

            # 回款
            rr = await db.execute(text("""
                SELECT COALESCE(SUM(amount), 0) FROM biz_finance_receipts WHERE receipt_date = :d
            """), {"d": target_date})
            total_receipt = float(rr.scalar() or 0)

            # 利润计算
            gross_profit = total_sales - total_cogs - (total_refund - total_refund_cogs)
            all_expense = total_ad + total_logistics + total_pack + total_commission + total_labor
            net_profit = gross_profit - all_expense
            profit_rate = (net_profit / total_sales * 100) if total_sales > 0 else 0
            total_fee_sum = sum(fee_map.values())
            cashflow_net = total_receipt - total_fee_sum

            # UPSERT
            await db.execute(text("""
                INSERT INTO fin_daily_summary (
                    biz_date, total_sales, total_refund, total_cogs, total_refund_cogs,
                    total_receipt, total_ad_cost, total_logistics, total_pack_cost,
                    total_commission, total_labor_cost, gross_profit, net_profit,
                    profit_rate, cashflow_net, store_count, created_at, updated_at
                ) VALUES (
                    :d, :sales, :refund, :cogs, :rcogs, :receipt,
                    :ad, :log, :pack, :comm, :labor,
                    :gp, :np, :pr, :cf, :sc, NOW(), NOW()
                )
                ON CONFLICT (biz_date) DO UPDATE SET
                    total_sales=EXCLUDED.total_sales, total_refund=EXCLUDED.total_refund,
                    total_cogs=EXCLUDED.total_cogs, total_refund_cogs=EXCLUDED.total_refund_cogs,
                    total_receipt=EXCLUDED.total_receipt, total_ad_cost=EXCLUDED.total_ad_cost,
                    total_logistics=EXCLUDED.total_logistics, total_pack_cost=EXCLUDED.total_pack_cost,
                    total_commission=EXCLUDED.total_commission, total_labor_cost=EXCLUDED.total_labor_cost,
                    gross_profit=EXCLUDED.gross_profit, net_profit=EXCLUDED.net_profit,
                    profit_rate=EXCLUDED.profit_rate, cashflow_net=EXCLUDED.cashflow_net,
                    store_count=EXCLUDED.store_count, updated_at=NOW()
            """), {
                "d": target_date, "sales": total_sales, "refund": total_refund,
                "cogs": total_cogs, "rcogs": total_refund_cogs, "receipt": total_receipt,
                "ad": total_ad, "log": total_logistics, "pack": total_pack,
                "comm": total_commission, "labor": round(total_labor, 2),
                "gp": round(gross_profit, 2), "np": round(net_profit, 2),
                "pr": round(profit_rate, 4), "cf": round(cashflow_net, 2), "sc": store_count,
            })
            await db.commit()
            logger.info(f"财务日汇总完成: {target_date}, 销售={total_sales}, 毛利={gross_profit:.2f}")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"财务日汇总失败 {target_date}: {e}")
            raise


async def scan_finance_risks(target_date: date = None):
    """
    扫描财务风险，生成预警记录到 fin_risk_alerts。
    检测规则：
      1. 退款率 > 15% → high_refund_rate (danger)
      2. 利润率 < 5% 且销售额 > 1000 → low_profit_rate (warning)
      3. 广告费占比 > 30% → high_ad_ratio (warning)
      4. 缺失成本价 SKU > 5 个 → missing_cost (info)
    """
    if not target_date:
        target_date = date.today() - timedelta(days=1)

    async with AsyncSessionLocal() as db:
        try:
            new_alerts = 0

            # 按店铺检查
            sr = await db.execute(text("""
                SELECT d.store_id, s.store_name,
                       d.sale_amount, d.refund_amount, d.sale_cogs,
                       d.refund_cogs, d.operating_profit, d.ad_cost,
                       d.missing_cost_skus
                FROM dm_store_daily d
                JOIN biz_stores s ON s.id = d.store_id
                WHERE d.biz_date = :d AND d.sale_amount > 0
            """), {"d": target_date})

            for row in sr.mappings():
                sales = float(row["sale_amount"] or 0)
                refund = float(row["refund_amount"] or 0)
                profit = float(row["operating_profit"] or 0)
                ad_cost = float(row["ad_cost"] or 0)
                missing = row["missing_cost_skus"] or []

                store_id = row["store_id"]
                store_name = row["store_name"]

                # 规则1: 退款率 > 15%
                if sales > 0:
                    refund_rate = refund / sales
                    if refund_rate > 0.15:
                        await _insert_alert(db, target_date, "high_refund_rate", "danger",
                            store_id, store_name, "退款率", 0.15, refund_rate,
                            f"{store_name} 退款率 {refund_rate*100:.1f}%，超过15%警戒线")
                        new_alerts += 1

                # 规则2: 利润率 < 5%
                if sales > 1000:
                    profit_rate = profit / sales
                    if profit_rate < 0.05:
                        await _insert_alert(db, target_date, "low_profit_rate", "warning",
                            store_id, store_name, "利润率", 0.05, profit_rate,
                            f"{store_name} 利润率 {profit_rate*100:.1f}%，低于5%")
                        new_alerts += 1

                # 规则3: 广告费占比 > 30%
                if sales > 0 and ad_cost > 0:
                    ad_ratio = ad_cost / sales
                    if ad_ratio > 0.30:
                        await _insert_alert(db, target_date, "high_ad_ratio", "warning",
                            store_id, store_name, "广告费占比", 0.30, ad_ratio,
                            f"{store_name} 广告费占销售额 {ad_ratio*100:.1f}%，超过30%")
                        new_alerts += 1

                # 规则4: 缺失成本 SKU > 5
                if isinstance(missing, list) and len(missing) > 5:
                    await _insert_alert(db, target_date, "missing_cost", "info",
                        store_id, store_name, "缺成本SKU数", 5, len(missing),
                        f"{store_name} 有 {len(missing)} 个SKU缺失成本价")
                    new_alerts += 1

            await db.commit()
            logger.info(f"财务风险扫描完成: {target_date}, 新增 {new_alerts} 条预警")
            return new_alerts

        except Exception as e:
            await db.rollback()
            logger.error(f"财务风险扫描失败: {e}")
            raise


async def _insert_alert(db, biz_date, alert_type, level, store_id, store_name,
                         metric_name, threshold, actual, message):
    """插入预警（同一天同类型同店铺不重复）"""
    exists = await db.execute(text("""
        SELECT 1 FROM fin_risk_alerts
        WHERE biz_date = :d AND alert_type = :t AND store_id = :s
        LIMIT 1
    """), {"d": biz_date, "t": alert_type, "s": store_id})
    if exists.scalar():
        return
    await db.execute(text("""
        INSERT INTO fin_risk_alerts (
            biz_date, alert_type, alert_level, store_id, store_name,
            metric_name, threshold, actual_value, message, created_at, updated_at
        ) VALUES (:d, :t, :l, :s, :sn, :mn, :th, :av, :msg, NOW(), NOW())
    """), {
        "d": biz_date, "t": alert_type, "l": level,
        "s": store_id, "sn": store_name,
        "mn": metric_name, "th": threshold, "av": actual, "msg": message,
    })
