"""
财务中心 - API 层
========================================
所有接口前缀: /api/v1/finance/
权限: finance (菜单级), finance:export/import/config/push (按钮级)
"""
from typing import Optional
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File as FileParam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance import FinanceReceipt, FinanceFee, FinCostConfig
from app.schemas.finance import (
    ReceiptCreate, FeeCreate, CostConfigCreate,
)
from app.services import finance_service
from app.core.permissions import check_permission


router = APIRouter(prefix="/finance/compass")


# ═══════════════════════════════════════════════════════════
# 1. 财务总览
# ═══════════════════════════════════════════════════════════

@router.get("/overview")
async def finance_overview(
    month: str = Query(None, description="YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """财务总览 KPI（11项指标 + 费用结构）"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return await finance_service.get_overview(db, month)


# ═══════════════════════════════════════════════════════════
# 2. 趋势
# ═══════════════════════════════════════════════════════════

@router.get("/trend")
async def finance_trend(
    month: str = Query(None, description="YYYY-MM"),
    months: int = Query(6, ge=3, le=12),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """近N个月销售/费用/利润趋势"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return await finance_service.get_trend(db, month, months)


# ═══════════════════════════════════════════════════════════
# 3. 店铺利润排行
# ═══════════════════════════════════════════════════════════

@router.get("/store-ranking")
async def store_ranking(
    month: str = Query(None),
    platform_id: Optional[int] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """店铺利润排行（按月）"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return await finance_service.get_store_ranking(db, month, platform_id, limit)


# ═══════════════════════════════════════════════════════════
# 4. 现金流日报
# ═══════════════════════════════════════════════════════════

@router.get("/cashflow-daily")
async def cashflow_daily(
    begin: date = Query(None),
    end: date = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """逐日现金流（回款-支出）"""
    if not end:
        end = date.today()
    if not begin:
        begin = end - timedelta(days=30)
    return await finance_service.get_cashflow_daily(db, begin, end)


# ═══════════════════════════════════════════════════════════
# 5. 财务明细
# ═══════════════════════════════════════════════════════════

@router.get("/details")
async def finance_details(
    month: str = Query(None),
    store_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """按日+店铺的财务明细表（分页）"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return await finance_service.get_details(db, month, store_id, page, page_size)


# ═══════════════════════════════════════════════════════════
# 6. 风险预警
# ═══════════════════════════════════════════════════════════

@router.get("/risk-alerts")
async def risk_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """财务风险预警列表"""
    return await finance_service.get_risk_alerts(db, unread_only, limit)


@router.put("/risk-alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """标记预警已读"""
    await finance_service.mark_alert_read(db, alert_id, current_user.id)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 7. 费用管理（保留并增强原有接口）
# ═══════════════════════════════════════════════════════════

@router.get("/fees")
async def list_fees(
    month: str = Query(None, description="YYYY-MM"),
    fee_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """费用明细列表"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    y, m = int(month[:4]), int(month[5:7])
    month_begin = date(y, m, 1)
    month_end = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    q = (select(FinanceFee)
         .where(FinanceFee.fee_date >= month_begin)
         .where(FinanceFee.fee_date < month_end)
         .order_by(FinanceFee.fee_date.desc()))
    if fee_type:
        q = q.where(FinanceFee.fee_type == fee_type)

    result = await db.execute(q)
    return [
        {
            "id":          f.id,
            "fee_date":    str(f.fee_date),
            "fee_type":    f.fee_type,
            "description": f.description,
            "store_name":  f.store_name or "",
            "amount":      float(f.amount or 0),
            "remark":      f.remark,
        }
        for f in result.scalars().all()
    ]


@router.post("/fees", status_code=201)
async def create_fee(
    body: FeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """录入费用"""
    f = FinanceFee(**body.model_dump(), created_by=current_user.id)
    db.add(f)
    await db.flush()
    await db.refresh(f)
    return {"id": f.id, "fee_date": str(f.fee_date), "amount": float(f.amount or 0)}


# ═══════════════════════════════════════════════════════════
# 8. 回款管理（保留原有接口）
# ═══════════════════════════════════════════════════════════

@router.get("/receipts")
async def list_receipts(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """回款记录列表"""
    result = await db.execute(
        select(FinanceReceipt).order_by(FinanceReceipt.receipt_date.desc()).limit(limit)
    )
    return [
        {
            "id":           r.id,
            "receipt_date": str(r.receipt_date),
            "platform":     r.platform or "",
            "store_name":   r.store_name or "",
            "amount":       float(r.amount or 0),
            "remark":       r.remark,
        }
        for r in result.scalars().all()
    ]


@router.post("/receipts", status_code=201)
async def create_receipt(
    body: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """录入回款"""
    r = FinanceReceipt(**body.model_dump(), created_by=current_user.id)
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return {"id": r.id, "receipt_date": str(r.receipt_date), "amount": float(r.amount or 0)}


# ═══════════════════════════════════════════════════════════
# 9. 月度汇总（保留兼容原有前端）
# ═══════════════════════════════════════════════════════════

@router.get("/summary")
async def finance_summary(
    month: str = Query(None, description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """月度汇总（兼容原有前端 index.vue 调用）"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    overview = await finance_service.get_overview(db, month)
    trend = await finance_service.get_trend(db, month, 6)

    return {
        "month":         month,
        "total_sale":    overview["total_sales"],
        "total_receipt": overview["total_receipt"],
        "total_cost":    overview["total_ad_cost"] + overview["total_logistics"]
                         + overview["total_pack_cost"] + overview["total_labor_cost"],
        "gross_profit":  overview["gross_profit"],
        "net_profit":    overview["net_profit"],
        "profit_rate":   overview["profit_rate"],
        "trend": {
            "months": [t["period"] for t in trend],
            "sales":  [t["sales"] for t in trend],
            "costs":  [t["cost"] for t in trend],
        },
    }


# ═══════════════════════════════════════════════════════════
# 10. 固定费用配置
# ═══════════════════════════════════════════════════════════

@router.get("/cost-config")
async def list_cost_config(
    month: str = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """月度固定费用配置列表"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    q = select(FinCostConfig).where(FinCostConfig.month == month)
    result = await db.execute(q)
    return [
        {
            "id":        c.id,
            "month":     c.month,
            "cost_type": c.cost_type,
            "amount":    float(c.amount or 0),
            "remark":    c.remark,
        }
        for c in result.scalars().all()
    ]


@router.post("/cost-config", status_code=201)
async def upsert_cost_config(
    body: CostConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """新增或更新月度固定费用（按 month+cost_type 唯一）"""
    # 检查权限
    if not check_permission(current_user, "finance:config"):
        raise HTTPException(status_code=403, detail="无权限: finance:config")

    # upsert
    existing = await db.execute(
        select(FinCostConfig)
        .where(FinCostConfig.month == body.month, FinCostConfig.cost_type == body.cost_type)
    )
    config = existing.scalar_one_or_none()
    if config:
        config.amount = body.amount
        config.remark = body.remark
    else:
        config = FinCostConfig(**body.model_dump())
        db.add(config)
    await db.flush()
    await db.refresh(config)
    return {"id": config.id, "month": config.month, "cost_type": config.cost_type, "amount": float(config.amount or 0)}


# ═══════════════════════════════════════════════════════════
# 11. 导出 Excel
# ═══════════════════════════════════════════════════════════

@router.get("/export/details")
async def export_details(
    month: str = Query(None),
    store_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """导出财务明细为 Excel"""
    if not check_permission(current_user, "finance:export"):
        raise HTTPException(status_code=403, detail="无权限: finance:export")
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"

    from app.services.finance_export_service import export_details as _export
    from fastapi.responses import Response
    content = await _export(db, month, store_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="finance_details_{month}.xlsx"'},
    )


@router.get("/export/store-ranking")
async def export_store_ranking(
    month: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """导出店铺排行为 Excel"""
    if not check_permission(current_user, "finance:export"):
        raise HTTPException(status_code=403, detail="无权限: finance:export")
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"

    from app.services.finance_export_service import export_store_ranking as _export
    from fastapi.responses import Response
    content = await _export(db, month)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="store_ranking_{month}.xlsx"'},
    )


# ═══════════════════════════════════════════════════════════
# 12. 费用导入
# ═══════════════════════════════════════════════════════════

@router.get("/import/fee-template")
async def download_fee_template(current_user = Depends(get_current_user)):
    """下载费用导入 Excel 模板"""
    from app.services.finance_export_service import generate_fee_import_template
    from fastapi.responses import Response
    content = generate_fee_import_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fee_import_template.xlsx"'},
    )



@router.post("/import/fees-upload")
async def import_fees_upload(
    file: UploadFile = FileParam(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """批量导入费用（上传 Excel 文件）"""
    if not check_permission(current_user, "finance:import"):
        raise HTTPException(status_code=403, detail="无权限: finance:import")

    content = await file.read()
    from app.services.finance_export_service import import_fees as _import
    result = await _import(db, content, current_user.id)
    return result
