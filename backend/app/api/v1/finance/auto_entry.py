"""
自动凭证生成 API
================
提供三类凭证的手动触发端点 + 一键月结端点。
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.services.finance_auto_entry_service import (
    gen_sales_voucher,
    gen_payroll_voucher,
    gen_depreciation_voucher,
    gen_all_month_entries,
)
from app.services.finance_voucher_service import VoucherValidationError

router = APIRouter(prefix="/finance")


class AutoEntryIn(BaseModel):
    book_id: int = 1
    period: str                 # YYYY-MM
    auto_post: bool = True      # 是否自动过账（默认审核后立即过账）


# ═══════════════════════════════════════════════════════════
# 1. 销售凭证（从 dm_store_daily 按月汇总）
# ═══════════════════════════════════════════════════════════

@router.post("/auto-entry/sales")
async def trigger_sales_voucher(
    body: AutoEntryIn,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    触发销售自动入账。
    从 dm_store_daily 按月汇总 net_sales / net_cogs / ad_cost，
    生成一张借贷平衡的销售凭证（同一 period 幂等，重复触发自动跳过）。
    """
    try:
        result = await gen_sales_voucher(
            db, book_id=body.book_id, period=body.period,
            operator=str(current_user.id), auto_post=body.auto_post,
        )
    except VoucherValidationError as e:
        raise HTTPException(400, str(e))
    return result


# ═══════════════════════════════════════════════════════════
# 2. 工资凭证（从 fin_payroll_records 按月汇总）
# ═══════════════════════════════════════════════════════════

@router.post("/auto-entry/payroll")
async def trigger_payroll_voucher(
    body: AutoEntryIn,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    触发工资凭证生成。
    汇总当月所有 voucher_id 为空的工资记录，计提应付职工薪酬，
    回写 voucher_id（同一 period 幂等）。
    """
    try:
        result = await gen_payroll_voucher(
            db, book_id=body.book_id, period=body.period,
            operator=str(current_user.id), auto_post=body.auto_post,
        )
    except VoucherValidationError as e:
        raise HTTPException(400, str(e))
    return result


# ═══════════════════════════════════════════════════════════
# 3. 折旧凭证（从 fin_fixed_assets 按月计提）
# ═══════════════════════════════════════════════════════════

@router.post("/auto-entry/depreciation")
async def trigger_depreciation_voucher(
    body: AutoEntryIn,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    触发折旧凭证生成。
    对所有 in_use 固定资产计提月折旧，更新 accumulated_depre 和 net_value，
    生成折旧凭证（同一 period 幂等）。
    """
    try:
        result = await gen_depreciation_voucher(
            db, book_id=body.book_id, period=body.period,
            operator=str(current_user.id), auto_post=body.auto_post,
        )
    except VoucherValidationError as e:
        raise HTTPException(400, str(e))
    return result


# ═══════════════════════════════════════════════════════════
# 4. 一键月结（三类全部触发）
# ═══════════════════════════════════════════════════════════

@router.post("/auto-entry/all")
async def trigger_all_entries(
    body: AutoEntryIn,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    一键生成当月所有自动凭证（销售 + 工资 + 折旧）。
    各类独立执行，某一类失败不影响其他类，返回各类执行摘要。
    """
    results = await gen_all_month_entries(
        db, book_id=body.book_id, period=body.period,
        operator=str(current_user.id),
    )
    success_count = sum(1 for r in results.values() if r.get("ok"))
    return {
        "period": body.period,
        "book_id": body.book_id,
        "success_count": success_count,
        "total": len(results),
        "details": results,
    }


# ═══════════════════════════════════════════════════════════
# 5. 查询待处理情况（预览，不执行）
# ═══════════════════════════════════════════════════════════

@router.get("/auto-entry/preview")
async def preview_auto_entries(
    book_id: int = Query(1),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    预览当月各类凭证可生成的数据摘要，不执行实际生成。
    """
    y, m = int(period[:4]), int(period[5:7])
    from datetime import date
    period_start = date(y, m, 1)
    period_end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

    # 销售数据
    sales_row = (await db.execute(
        text("""
            SELECT COALESCE(SUM(sale_amount),0) AS sale, COALESCE(SUM(refund_amount),0) AS refund,
                   COALESCE(SUM(sale_cogs),0) AS cogs, COALESCE(SUM(refund_cogs),0) AS rcogs,
                   COALESCE(SUM(ad_cost),0) AS ad
            FROM dm_store_daily WHERE biz_date >= :s AND biz_date < :e
        """),
        {"s": period_start, "e": period_end}
    )).mappings().one()

    # 工资待处理
    from app.models.finance.business import FinPayrollRecord
    payroll_q = await db.execute(
        select(FinPayrollRecord).where(
            FinPayrollRecord.book_id == book_id,
            FinPayrollRecord.pay_month == period,
            FinPayrollRecord.voucher_id.is_(None),
        )
    )
    payroll_records = payroll_q.scalars().all()

    # 固定资产
    from app.models.finance.business import FinFixedAsset
    assets_q = await db.execute(
        select(FinFixedAsset).where(
            FinFixedAsset.book_id == book_id,
            FinFixedAsset.status == "in_use",
            FinFixedAsset.monthly_depre > 0,
        )
    )
    assets = assets_q.scalars().all()

    # 已生成凭证检查
    from app.models.finance.accounting import FinVoucher
    existing = {}
    for stype in ["jst_sales", "payroll", "depreciation"]:
        v = await db.scalar(
            select(FinVoucher).where(
                FinVoucher.book_id == book_id,
                FinVoucher.source_type == stype,
                FinVoucher.source_ref == f"{stype.replace('jst_', '')}-{period}",
            )
        )
        existing[stype] = v.voucher_no if v else None

    return {
        "period": period,
        "book_id": book_id,
        "sales": {
            "net_sales": float(sales_row["sale"]) - float(sales_row["refund"]),
            "net_cogs":  float(sales_row["cogs"]) - float(sales_row["rcogs"]),
            "ad_cost":   float(sales_row["ad"]),
            "already_generated": existing["jst_sales"],
        },
        "payroll": {
            "pending_records": len(payroll_records),
            "total_gross": sum(float(r.gross_pay or 0) for r in payroll_records),
            "already_generated": existing["payroll"],
        },
        "depreciation": {
            "asset_count": len(assets),
            "total_monthly_depre": sum(float(a.monthly_depre or 0) for a in assets),
            "already_generated": existing["depreciation"],
        },
    }
