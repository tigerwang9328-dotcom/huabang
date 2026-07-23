"""
自动凭证生成服务
================
对标虎狼 finance/auto_entry.py，全面迁移为 async PostgreSQL 版本。
支持三类自动凭证：
  1. gen_sales_voucher()       — 从 dm_store_daily 按月汇总生成销售收入+成本凭证
  2. gen_payroll_voucher()     — 从 fin_payroll_records 生成当月工资凭证
  3. gen_depreciation_voucher() — 从 fin_fixed_assets 生成月折旧凭证

所有函数返回 {"ok": True, "voucher_id": x, "message": "..."} 或 {"ok": False, "message": "..."}
去重逻辑：通过 fin_vouchers.source_type + source_ref 判断是否已生成。
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.models.finance.accounting import FinAccount, FinVoucher
from app.models.finance.business import FinPayrollRecord, FinFixedAsset
from app.services.finance_voucher_service import create_voucher, post, VoucherValidationError


# ── 工具：按编码找科目 ID ────────────────────────────────────────────────────

async def _acct(db: AsyncSession, book_id: int, code: str) -> Optional[int]:
    """按科目编码查找科目ID，不存在返回None"""
    row = await db.scalar(
        select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.account_code == code)
    )
    return row.id if row else None


async def _require_acct(db: AsyncSession, book_id: int, code: str) -> int:
    aid = await _acct(db, book_id, code)
    if not aid:
        raise VoucherValidationError(f"科目 {code} 不存在，请先初始化科目体系")
    return aid


async def _already_exists(db: AsyncSession, book_id: int, source_type: str, source_ref: str) -> bool:
    """去重检查：同 source_type + source_ref 的凭证已存在则跳过"""
    v = await db.scalar(
        select(FinVoucher).where(
            FinVoucher.book_id == book_id,
            FinVoucher.source_type == source_type,
            FinVoucher.source_ref == source_ref,
        )
    )
    return v is not None


# ══════════════════════════════════════════════════════════════
# 1. 销售凭证（从 dm_store_daily 按月汇总）
# ══════════════════════════════════════════════════════════════

async def gen_sales_voucher(
    db: AsyncSession,
    book_id: int,
    period: str,     # YYYY-MM
    operator: str = "system",
    auto_post: bool = True,
) -> dict:
    """
    从 dm_store_daily 按期间汇总销售数据，生成销售收入+成本凭证。
    凭证结构：
      借 1122 应收账款         net_sales（sale_amount - refund_amount）
      贷 6001 主营业务收入     net_sales
      借 6401 主营业务成本     net_cogs（sale_cogs - refund_cogs）
      贷 1405 库存商品         net_cogs
      借 6601 销售费用（广告） ad_cost（若 ad_cost > 0）
      贷 2202 应付账款         ad_cost
    """
    source_ref = f"sales-{period}"
    if await _already_exists(db, book_id, "jst_sales", source_ref):
        return {"ok": False, "message": f"期间 {period} 销售凭证已生成，跳过"}

    y, m = int(period[:4]), int(period[5:7])
    period_start = date(y, m, 1)
    if m == 12:
        period_end = date(y + 1, 1, 1)
    else:
        period_end = date(y, m + 1, 1)

    # 汇总销售数据
    result = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(sale_amount), 0)    AS sale_amount,
                COALESCE(SUM(refund_amount), 0)  AS refund_amount,
                COALESCE(SUM(sale_cogs), 0)      AS sale_cogs,
                COALESCE(SUM(refund_cogs), 0)    AS refund_cogs,
                COALESCE(SUM(ad_cost), 0)        AS ad_cost
            FROM dm_store_daily
            WHERE biz_date >= :start AND biz_date < :end
        """),
        {"start": period_start, "end": period_end},
    )
    row = result.mappings().one()
    net_sales = Decimal(str(row["sale_amount"])) - Decimal(str(row["refund_amount"]))
    net_cogs   = Decimal(str(row["sale_cogs"]))  - Decimal(str(row["refund_cogs"]))
    ad_cost    = Decimal(str(row["ad_cost"]))

    if net_sales <= 0 and net_cogs <= 0 and ad_cost <= 0:
        return {"ok": False, "message": f"期间 {period} 无销售数据，未生成凭证"}

    lines = []

    # 销售收入分录
    if net_sales > 0:
        recv_id  = await _require_acct(db, book_id, "1122")
        rev_id   = await _require_acct(db, book_id, "6001")
        lines += [
            {"account_id": recv_id, "account_code": "1122",
             "debit_amount": net_sales, "credit_amount": Decimal("0"),
             "summary": f"{period} 销售收入（含退款净额）"},
            {"account_id": rev_id,  "account_code": "6001",
             "debit_amount": Decimal("0"), "credit_amount": net_sales,
             "summary": f"{period} 主营业务收入"},
        ]

    # 销售成本分录
    if net_cogs > 0:
        cogs_id  = await _require_acct(db, book_id, "6401")
        inv_id   = await _require_acct(db, book_id, "1405")
        lines += [
            {"account_id": cogs_id, "account_code": "6401",
             "debit_amount": net_cogs, "credit_amount": Decimal("0"),
             "summary": f"{period} 主营业务成本"},
            {"account_id": inv_id,  "account_code": "1405",
             "debit_amount": Decimal("0"), "credit_amount": net_cogs,
             "summary": f"{period} 结转库存商品"},
        ]

    # 广告费用分录
    if ad_cost > 0:
        exp_id = await _require_acct(db, book_id, "6601")
        pay_id = await _require_acct(db, book_id, "2202")
        lines += [
            {"account_id": exp_id, "account_code": "6601",
             "debit_amount": ad_cost, "credit_amount": Decimal("0"),
             "summary": f"{period} 广告推广费"},
            {"account_id": pay_id, "account_code": "2202",
             "debit_amount": Decimal("0"), "credit_amount": ad_cost,
             "summary": f"{period} 应付广告费"},
        ]

    voucher_date = date(y, m, 1)  # 记在月初
    v = await create_voucher(
        db,
        book_id=book_id,
        voucher_type="记",
        voucher_date=voucher_date,
        lines=lines,
        summary=f"{period} 销售业务自动入账",
        source_type="jst_sales",
        source_ref=source_ref,
        status="reviewed",
        operator=operator,
    )

    if auto_post:
        v = await post(db, v.id, operator)

    await db.commit()
    return {
        "ok": True,
        "voucher_id": v.id,
        "voucher_no": v.voucher_no,
        "message": f"已生成销售凭证 {v.voucher_no}（净销售 {net_sales}，净成本 {net_cogs}，广告 {ad_cost}）",
    }


# ══════════════════════════════════════════════════════════════
# 2. 工资凭证（从 fin_payroll_records 按月汇总）
# ══════════════════════════════════════════════════════════════

async def gen_payroll_voucher(
    db: AsyncSession,
    book_id: int,
    period: str,     # YYYY-MM（pay_month）
    operator: str = "system",
    auto_post: bool = True,
) -> dict:
    """
    汇总当月所有未生成凭证的工资记录，生成工资凭证。
    凭证结构（按 cost_type 分组）：
      借 6602 管理费用          管理类 gross_pay 合计
      借 6601 销售费用          销售类 gross_pay 合计
      贷 2211 应付职工薪酬      gross_pay 总合计
    后续实际发放凭证（另行手工处理）：
      借 2211 应付职工薪酬 / 贷 1002 银行存款  net_pay
    """
    source_ref = f"payroll-{period}"
    if await _already_exists(db, book_id, "payroll", source_ref):
        return {"ok": False, "message": f"期间 {period} 工资凭证已生成，跳过"}

    result = await db.execute(
        select(FinPayrollRecord).where(
            FinPayrollRecord.book_id == book_id,
            FinPayrollRecord.pay_month == period,
            FinPayrollRecord.voucher_id.is_(None),
        )
    )
    records = result.scalars().all()

    if not records:
        return {"ok": False, "message": f"期间 {period} 无待处理工资记录（或已关联凭证）"}

    # 按 cost_type 汇总 gross_pay
    admin_total = Decimal("0")
    sales_total = Decimal("0")
    for r in records:
        gp = Decimal(str(r.gross_pay or 0))
        if r.cost_type == "销售费用":
            sales_total += gp
        else:
            admin_total += gp

    total_gross = admin_total + sales_total
    if total_gross <= 0:
        return {"ok": False, "message": f"期间 {period} 工资总额为零，未生成凭证"}

    lines = []
    if admin_total > 0:
        aid = await _require_acct(db, book_id, "6602")
        lines.append({
            "account_id": aid, "account_code": "6602",
            "debit_amount": admin_total, "credit_amount": Decimal("0"),
            "summary": f"{period} 管理人员工资",
        })
    if sales_total > 0:
        sid = await _require_acct(db, book_id, "6601")
        lines.append({
            "account_id": sid, "account_code": "6601",
            "debit_amount": sales_total, "credit_amount": Decimal("0"),
            "summary": f"{period} 销售人员工资",
        })

    payable_id = await _require_acct(db, book_id, "2211")
    lines.append({
        "account_id": payable_id, "account_code": "2211",
        "debit_amount": Decimal("0"), "credit_amount": total_gross,
        "summary": f"{period} 计提应付职工薪酬",
    })

    y, m = int(period[:4]), int(period[5:7])
    # 工资凭证记在月末最后一天
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    voucher_date = date(y, m, last_day)

    v = await create_voucher(
        db,
        book_id=book_id,
        voucher_type="记",
        voucher_date=voucher_date,
        lines=lines,
        summary=f"{period} 工资自动入账（{len(records)} 人，合计 {total_gross}）",
        source_type="payroll",
        source_ref=source_ref,
        status="reviewed",
        operator=operator,
    )

    if auto_post:
        v = await post(db, v.id, operator)

    # 回写 voucher_id 到工资记录
    for r in records:
        r.voucher_id = v.id

    await db.flush()
    await db.commit()
    return {
        "ok": True,
        "voucher_id": v.id,
        "voucher_no": v.voucher_no,
        "employee_count": len(records),
        "total_gross": float(total_gross),
        "message": f"已生成工资凭证 {v.voucher_no}（{len(records)} 人，共 {total_gross} 元）",
    }


# ══════════════════════════════════════════════════════════════
# 3. 折旧凭证（从 fin_fixed_assets 按月计提）
# ══════════════════════════════════════════════════════════════

# 固定资产类别 → 折旧计入科目
_DEPRE_EXPENSE_MAP = {
    "办公设备":   "6602",  # 管理费用
    "生产设备":   "6401",  # 制造费用（简化：直接计入主营成本）
    "运输工具":   "6601",  # 销售费用
    "电子设备":   "6602",  # 管理费用
    "其他":       "6602",  # 默认管理费用
}


async def gen_depreciation_voucher(
    db: AsyncSession,
    book_id: int,
    period: str,
    operator: str = "system",
    auto_post: bool = True,
) -> dict:
    """
    对所有 in_use 固定资产计提当月折旧，生成折旧凭证，并更新资产的累计折旧和净值。
    凭证结构（按费用科目合并）：
      借 6602/6601 管理/销售费用   monthly_depre 合计
      贷 1602 累计折旧             月折旧总额
    """
    source_ref = f"depre-{period}"
    if await _already_exists(db, book_id, "depreciation", source_ref):
        return {"ok": False, "message": f"期间 {period} 折旧凭证已生成，跳过"}

    result = await db.execute(
        select(FinFixedAsset).where(
            FinFixedAsset.book_id == book_id,
            FinFixedAsset.status == "in_use",
            FinFixedAsset.monthly_depre > 0,
        )
    )
    assets = result.scalars().all()

    if not assets:
        return {"ok": False, "message": f"账套 {book_id} 无在用固定资产，未生成折旧凭证"}

    # 按费用科目分组累计折旧额
    expense_totals: dict[str, Decimal] = {}
    total_depre = Decimal("0")

    for asset in assets:
        monthly = Decimal(str(asset.monthly_depre or 0))
        if monthly <= 0:
            continue
        category = asset.category or "其他"
        expense_code = _DEPRE_EXPENSE_MAP.get(category, "6602")
        expense_totals[expense_code] = expense_totals.get(expense_code, Decimal("0")) + monthly
        total_depre += monthly

    if total_depre <= 0:
        return {"ok": False, "message": "月折旧额合计为零"}

    lines = []
    for code, amount in expense_totals.items():
        acct_id = await _require_acct(db, book_id, code)
        lines.append({
            "account_id": acct_id, "account_code": code,
            "debit_amount": amount, "credit_amount": Decimal("0"),
            "summary": f"{period} 计提折旧",
        })

    acc_depre_id = await _require_acct(db, book_id, "1602")
    lines.append({
        "account_id": acc_depre_id, "account_code": "1602",
        "debit_amount": Decimal("0"), "credit_amount": total_depre,
        "summary": f"{period} 固定资产折旧（{len(assets)} 项）",
    })

    y, m = int(period[:4]), int(period[5:7])
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    voucher_date = date(y, m, last_day)

    v = await create_voucher(
        db,
        book_id=book_id,
        voucher_type="记",
        voucher_date=voucher_date,
        lines=lines,
        summary=f"{period} 折旧计提（{len(assets)} 项资产，合计 {total_depre}）",
        source_type="depreciation",
        source_ref=source_ref,
        status="reviewed",
        operator=operator,
    )

    if auto_post:
        v = await post(db, v.id, operator)

    # 更新资产累计折旧和净值
    for asset in assets:
        monthly = Decimal(str(asset.monthly_depre or 0))
        asset.accumulated_depre = Decimal(str(asset.accumulated_depre or 0)) + monthly
        asset.net_value = max(
            Decimal(str(asset.original_value or 0)) - asset.accumulated_depre,
            Decimal("0"),
        )

    await db.flush()
    await db.commit()
    return {
        "ok": True,
        "voucher_id": v.id,
        "voucher_no": v.voucher_no,
        "asset_count": len(assets),
        "total_depre": float(total_depre),
        "message": f"已生成折旧凭证 {v.voucher_no}（{len(assets)} 项资产，共 {total_depre} 元）",
    }


# ══════════════════════════════════════════════════════════════
# 4. 一键月结（三类凭证全部触发）
# ══════════════════════════════════════════════════════════════

async def gen_all_month_entries(
    db: AsyncSession,
    book_id: int,
    period: str,
    operator: str = "system",
) -> dict:
    """一键生成当月所有自动凭证（销售+工资+折旧），返回各类执行结果。"""
    results = {}
    for name, fn in [
        ("sales",       gen_sales_voucher),
        ("payroll",     gen_payroll_voucher),
        ("depreciation", gen_depreciation_voucher),
    ]:
        try:
            results[name] = await fn(db, book_id, period, operator=operator, auto_post=True)
        except VoucherValidationError as e:
            results[name] = {"ok": False, "message": str(e)}
        except Exception as e:
            results[name] = {"ok": False, "message": f"意外错误：{e}"}
    return results
