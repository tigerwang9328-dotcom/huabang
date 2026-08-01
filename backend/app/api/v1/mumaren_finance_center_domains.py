"""Independent Mumaren AR/AP and tax read/write APIs.

These endpoints operate only on the isolated ``finance_center_mumaren`` schema.
They do not create vouchers and never call the legacy Huabang finance routers.
The write path follows the fixed "draft → finance review → manual settle/pay"
flow and never auto-generates or posts accounting entries.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mumaren_finance_center import (
    require_mumaren_finance_access,
    require_mumaren_voucher_post,
    require_mumaren_voucher_review,
    require_mumaren_voucher_write,
)
from app.core.database import get_db
from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenFiscalPeriod,
    FinanceCenterMumarenVoucher,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenCashAccount,
    FinanceCenterMumarenCashFlow,
    FinanceCenterMumarenFixedAsset,
    FinanceCenterMumarenInvoice,
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenPayroll,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)
from app.services.mumaren_finance_center.business import depreciation_for_period
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.mumaren_finance_center.ar_ap import (
    CrossBookViolationError,
    InvalidOrderTransition,
    build_aging,
    create_ar_ap_order,
    review_ar_ap_order,
    settle_ar_ap_order,
)
from app.services.mumaren_finance_center.tax import (
    CrossBookTaxViolationError,
    InvalidTaxTransition,
    build_tax_alerts,
    create_tax_record,
    pay_tax_record,
    review_tax_record,
    tax_record_balance,
)


router = APIRouter(prefix="/finance-center/mumaren", tags=["牧马人财务中心：往来与税务"])


def _actor_id(user: SysUser) -> int:
    return int(user.id)


class ArApOrderInput(BaseModel):
    book_id: int = Field(ge=1)
    order_type: str = Field(pattern=r"^(receivable|payable)$")
    order_no: str = Field(min_length=1, max_length=64)
    order_date: date
    counterparty_id: int | None = Field(default=None, ge=1)
    counterparty_name: str = Field(min_length=1, max_length=128)
    total_amount: Decimal = Field(ge=0)
    remark: str | None = Field(default=None, max_length=500)


class ArApSettleInput(BaseModel):
    settlement_date: date
    amount: Decimal = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)


class TaxRecordInput(BaseModel):
    book_id: int = Field(ge=1)
    tax_type_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    tax_amount: Decimal = Field(ge=0)
    due_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)


class TaxPayInput(BaseModel):
    payment_date: date
    amount: Decimal = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)


def _order_data(order) -> dict:
    return {
        "id": order.id,
        "book_id": order.book_id,
        "order_type": getattr(order, "settlement_type", None) or type(order).__name__,
        "order_no": order.order_no,
        "order_date": order.order_date,
        "counterparty_id": order.counterparty_id,
        "counterparty_name": order.counterparty_name,
        "total_amount": order.total_amount,
        "settled_amount": order.settled_amount,
        "settlement_status": order.settlement_status,
        "workflow_status": order.workflow_status,
    }


def _tax_record_data(record, *, tax_code=None, tax_name=None) -> dict:
    return {
        "id": record.id,
        "book_id": record.book_id,
        "tax_type_id": record.tax_type_id,
        "tax_code": tax_code,
        "tax_name": tax_name,
        "period": record.period,
        "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "unpaid_amount": tax_record_balance(record.tax_amount, record.paid_amount),
        "due_date": record.due_date,
        "status": record.status,
        "workflow_status": record.workflow_status,
    }


@router.get("/ar-ap/aging", response_model=ApiResponse)
async def get_ar_ap_aging(
    book_id: int = Query(ge=1),
    order_type: str = Query(default="receivable", pattern=r"^(receivable|payable)$"),
    as_of: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Return ageing derived only from current, isolated AR/AP orders."""
    model = FinanceCenterMumarenReceivableOrder if order_type == "receivable" else FinanceCenterMumarenPayableOrder
    rows = list((await db.execute(
        select(model).where(model.book_id == book_id).order_by(model.order_date, model.id).limit(limit)
    )).scalars())
    result = build_aging(({
        "counterparty_name": row.counterparty_name,
        "order_no": row.order_no,
        "order_date": row.order_date,
        "total_amount": row.total_amount,
        "settled_amount": row.settled_amount,
    } for row in rows), as_of=as_of or date.today())
    return ApiResponse.ok(data={"order_type": order_type, **result})


@router.get("/tax-types", response_model=ApiResponse)
async def list_tax_types(
    book_id: int = Query(ge=1),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """List active tax types configured for one isolated finance book."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxType)
        .where(
            FinanceCenterMumarenTaxType.book_id == book_id,
            FinanceCenterMumarenTaxType.is_active.is_(True),
        )
        .order_by(FinanceCenterMumarenTaxType.tax_code, FinanceCenterMumarenTaxType.id)
    )).scalars().all())
    return ApiResponse.ok(data=[{
        "id": row.id,
        "tax_code": row.tax_code,
        "tax_name": row.tax_name,
        "default_rate": float(row.default_rate),
    } for row in rows])


@router.get("/tax/alerts", response_model=ApiResponse)
async def get_tax_alerts(
    book_id: int = Query(ge=1),
    today: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Return unpaid/near-due tax alerts without creating accounting entries."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxRecord, FinanceCenterMumarenTaxType.tax_name)
        .join(FinanceCenterMumarenTaxType, FinanceCenterMumarenTaxType.id == FinanceCenterMumarenTaxRecord.tax_type_id)
        .where(FinanceCenterMumarenTaxRecord.book_id == book_id)
        .order_by(FinanceCenterMumarenTaxRecord.due_date, FinanceCenterMumarenTaxRecord.id)
        .limit(limit)
    )).all())
    records = [{
        "tax_name": tax_name,
        "period": record.period,
        "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "due_date": record.due_date,
    } for record, tax_name in rows]
    alerts = build_tax_alerts(records, today=today or date.today())
    return ApiResponse.ok(data={"alerts": alerts, "record_count": len(records)})


@router.get("/tax/records", response_model=ApiResponse)
async def get_tax_records(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """List isolated tax records and calculated unpaid balances."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxRecord, FinanceCenterMumarenTaxType.tax_code, FinanceCenterMumarenTaxType.tax_name)
        .join(FinanceCenterMumarenTaxType, FinanceCenterMumarenTaxType.id == FinanceCenterMumarenTaxRecord.tax_type_id)
        .where(FinanceCenterMumarenTaxRecord.book_id == book_id)
        .order_by(FinanceCenterMumarenTaxRecord.period.desc(), FinanceCenterMumarenTaxRecord.id.desc())
        .limit(limit)
    )).all())
    return ApiResponse.ok(data=[{
        "id": record.id, "tax_code": tax_code, "tax_name": tax_name,
        "period": record.period, "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "unpaid_amount": tax_record_balance(record.tax_amount, record.paid_amount),
        "due_date": record.due_date, "status": record.status,
        "workflow_status": record.workflow_status,
    } for record, tax_code, tax_name in rows])


# ---------------------------------------------------------------------------
# AR/AP 写入端点:草稿 → 财务审核 → 人工结算(不产生任何凭证分录)
# ---------------------------------------------------------------------------

@router.post("/ar-ap/orders", response_model=ApiResponse)
async def create_ar_ap_order_endpoint(
    body: ArApOrderInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建 AR/AP 草稿单据;强制同账簿校验,不自动生成凭证。"""
    try:
        order = await create_ar_ap_order(
            db,
            book_id=body.book_id,
            order_type=body.order_type,
            order_no=body.order_no,
            order_date=body.order_date,
            counterparty_id=body.counterparty_id,
            counterparty_name=body.counterparty_name,
            total_amount=body.total_amount,
            operator_id=_actor_id(current_user),
            remark=body.remark,
        )
    except CrossBookViolationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=body.book_id, action="create_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"创建{body.order_type}单据 {body.order_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 草稿已创建")


@router.post("/ar-ap/orders/{order_id}/review", response_model=ApiResponse)
async def review_ar_ap_order_endpoint(
    order_id: int,
    order_type: Literal["receivable", "payable"] = Query(),
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    """财务审核 AR/AP 草稿;仅 draft → reviewed,不产生凭证分录。"""
    try:
        order = await review_ar_ap_order(
            db, order_id=order_id, order_type=order_type, operator_id=_actor_id(current_user),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _add_audit_log(
        db, book_id=order.book_id, action="review_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"审核AR/AP单据 {order_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已审核")


@router.post("/ar-ap/orders/{order_id}/settle", response_model=ApiResponse)
async def settle_ar_ap_order_endpoint(
    order_id: int,
    body: ArApSettleInput,
    order_type: Literal["receivable", "payable"] = Query(),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """人工结算 AR/AP 单据;防超额,不产生凭证分录。"""
    try:
        order = await settle_ar_ap_order(
            db, order_id=order_id, order_type=order_type,
            settlement_date=body.settlement_date, amount=body.amount,
            operator_id=_actor_id(current_user), remark=body.remark,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=order.book_id, action="settle_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"结算AR/AP单据 {order_id} 金额 {body.amount}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已结算")


async def _review_ar_ap_with_fallback(db: AsyncSession, *, order_id: int, operator_id: int):
    """按 order_id 尝试 receivable/payable 两种模型审核。"""
    for order_type in ("receivable", "payable"):
        try:
            return await review_ar_ap_order(db, order_id=order_id, order_type=order_type, operator_id=operator_id)
        except LookupError:
            continue
    raise LookupError(f"AR/AP 单据 {order_id} 不存在")


async def _settle_ar_ap_with_fallback(db: AsyncSession, *, order_id: int, settlement_date: date, amount, operator_id: int, remark: str | None = None):
    """按 order_id 尝试 receivable/payable 两种模型结算。"""
    for order_type in ("receivable", "payable"):
        try:
            return await settle_ar_ap_order(
                db, order_id=order_id, order_type=order_type,
                settlement_date=settlement_date, amount=amount,
                operator_id=operator_id, remark=remark,
            )
        except LookupError:
            continue
    raise LookupError(f"AR/AP 单据 {order_id} 不存在")


# ---------------------------------------------------------------------------
# 税务写入端点:草稿 → 财务审核 → 人工缴税(不产生任何凭证分录)
# ---------------------------------------------------------------------------

@router.post("/tax/records", response_model=ApiResponse)
async def create_tax_record_endpoint(
    body: TaxRecordInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建税务草稿单据;强制同账簿校验,不自动生成凭证。"""
    try:
        record = await create_tax_record(
            db,
            book_id=body.book_id,
            tax_type_id=body.tax_type_id,
            period=body.period,
            tax_amount=body.tax_amount,
            operator_id=_actor_id(current_user),
            due_date=body.due_date,
            remark=body.remark,
        )
    except CrossBookTaxViolationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=body.book_id, action="create_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"创建税务记录 期间 {body.period}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务草稿已创建")


@router.post("/tax/records/{record_id}/review", response_model=ApiResponse)
async def review_tax_record_endpoint(
    record_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    """财务审核税务草稿;仅 draft → reviewed,不产生凭证分录。"""
    try:
        record = await review_tax_record(db, record_id=record_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidTaxTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _add_audit_log(
        db, book_id=record.book_id, action="review_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"审核税务记录 {record_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务单据已审核")


@router.post("/tax/records/{record_id}/pay", response_model=ApiResponse)
async def pay_tax_record_endpoint(
    record_id: int,
    body: TaxPayInput,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """人工缴税;防超额,不产生凭证分录。"""
    try:
        record = await pay_tax_record(
            db, record_id=record_id, payment_date=body.payment_date,
            amount=body.amount, operator_id=_actor_id(current_user), remark=body.remark,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidTaxTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=record.book_id, action="pay_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"缴税 {record_id} 金额 {body.amount}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务单据已缴税")


# ===========================================================================
# 通用审计日志写入助手:确保与主操作在同一事务内 flush
# ===========================================================================

def _add_audit_log(
    db: AsyncSession,
    *,
    book_id: int | None,
    action: str,
    operator_id: int,
    detail: str | None = None,
    voucher_id: int | None = None,
) -> None:
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id,
        voucher_id=voucher_id,
        action=action,
        operator_id=operator_id,
        detail=detail,
    ))


def _period_code_from_date(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


# ===========================================================================
# Task 2: 固定资产 CRUD(复用 finance_center_mumaren_fixed_assets)
# ===========================================================================

class FixedAssetInput(BaseModel):
    book_id: int = Field(ge=1)
    asset_code: str = Field(min_length=1, max_length=64)
    asset_name: str = Field(min_length=1, max_length=255)
    asset_category: str | None = Field(default=None, max_length=64)
    purchase_date: date
    original_value: Decimal = Field(ge=0)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    useful_life_months: int = Field(ge=1)


class FixedAssetUpdate(BaseModel):
    book_id: int = Field(ge=1)
    asset_name: str | None = None
    asset_category: str | None = None
    purchase_date: date | None = None
    original_value: Decimal | None = Field(default=None, ge=0)
    residual_value: Decimal | None = Field(default=None, ge=0)
    useful_life_months: int | None = Field(default=None, ge=1)
    status: Literal["disposed"] | None = None


def _fixed_asset_data(asset: FinanceCenterMumarenFixedAsset) -> dict:
    return {
        "id": asset.id,
        "book_id": asset.book_id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "asset_category": asset.asset_category,
        "purchase_date": asset.purchase_date,
        "original_value": asset.original_value,
        "residual_value": asset.residual_value,
        "useful_life_months": asset.useful_life_months,
        "accumulated_depreciation": asset.accumulated_depreciation,
        "status": asset.status,
    }


@router.get("/fixed-assets", response_model=ApiResponse)
async def list_fixed_assets(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出固定资产,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenFixedAsset)
        .where(FinanceCenterMumarenFixedAsset.book_id == book_id)
        .order_by(FinanceCenterMumarenFixedAsset.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_fixed_asset_data(row) for row in rows])


@router.post("/fixed-assets", response_model=ApiResponse)
async def create_fixed_asset(
    body: FixedAssetInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建固定资产(初始 draft);不自动审核、不自动过账。"""
    asset = FinanceCenterMumarenFixedAsset(
        book_id=body.book_id,
        asset_code=body.asset_code,
        asset_name=body.asset_name,
        asset_category=body.asset_category,
        purchase_date=body.purchase_date,
        original_value=body.original_value,
        residual_value=body.residual_value,
        useful_life_months=body.useful_life_months,
        accumulated_depreciation=Decimal("0"),
        status="draft",
    )
    db.add(asset)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"创建固定资产 {body.asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="固定资产已创建")


@router.put("/fixed-assets/{asset_id}", response_model=ApiResponse)
async def update_fixed_asset(
    asset_id: int,
    body: FixedAssetUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新固定资产(仅 draft 或 active 状态可改);强制同账簿校验。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if asset.status not in ("draft", "active"):
        raise HTTPException(status_code=409, detail=f"当前状态 {asset.status},不可修改")
    for field in ("asset_name", "asset_category", "purchase_date", "original_value", "residual_value", "useful_life_months"):
        value = getattr(body, field)
        if value is not None:
            setattr(asset, field, value)
    if body.status is not None:
        asset.status = body.status
    await db.flush()
    _add_audit_log(
        db, book_id=asset.book_id, action="update_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"更新固定资产 {asset.asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="固定资产已更新")


@router.delete("/fixed-assets/{asset_id}", response_model=ApiResponse)
async def delete_fixed_asset(
    asset_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除固定资产(仅 draft 可删);强制同账簿校验。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if asset.status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {asset.status},仅 draft 可删除")
    asset_code = asset.asset_code
    await db.delete(asset)
    _add_audit_log(
        db, book_id=book_id, action="delete_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"删除固定资产 {asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(message="固定资产已删除")


@router.post("/fixed-assets/{asset_id}/depreciate", response_model=ApiResponse)
async def depreciate_fixed_asset(
    asset_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """月折旧计提:accumulated_depreciation += (原值-残值)/使用月数,封顶在可折旧额。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    try:
        monthly = depreciation_for_period(
            original_value=asset.original_value,
            residual_value=asset.residual_value,
            useful_life_months=asset.useful_life_months,
            already_depreciated=asset.accumulated_depreciation,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    asset.accumulated_depreciation = Decimal(asset.accumulated_depreciation) + monthly
    await db.flush()
    _add_audit_log(
        db, book_id=asset.book_id, action="depreciate_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"计提折旧 {asset.asset_code} 本次 {monthly}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="折旧已计提")


# ===========================================================================
# Task 3: 发票 CRUD(复用 finance_center_mumaren_invoices)
# ===========================================================================

class InvoiceInput(BaseModel):
    book_id: int = Field(ge=1)
    invoice_no: str = Field(min_length=1, max_length=64)
    invoice_type: str = Field(min_length=1, max_length=32)
    invoice_date: date
    counterparty_name: str | None = Field(default=None, max_length=128)
    amount: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)


class InvoiceUpdate(BaseModel):
    book_id: int = Field(ge=1)
    invoice_type: str | None = None
    invoice_date: date | None = None
    counterparty_name: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)


def _invoice_data(invoice: FinanceCenterMumarenInvoice) -> dict:
    return {
        "id": invoice.id,
        "book_id": invoice.book_id,
        "invoice_no": invoice.invoice_no,
        "invoice_type": invoice.invoice_type,
        "invoice_date": invoice.invoice_date,
        "counterparty_name": invoice.counterparty_name,
        "amount": invoice.amount,
        "tax_amount": invoice.tax_amount,
        "verification_status": invoice.verification_status,
        "workflow_status": invoice.workflow_status,
    }


@router.get("/invoices", response_model=ApiResponse)
async def list_invoices(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出发票,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenInvoice)
        .where(FinanceCenterMumarenInvoice.book_id == book_id)
        .order_by(FinanceCenterMumarenInvoice.invoice_date.desc(), FinanceCenterMumarenInvoice.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_invoice_data(row) for row in rows])


@router.post("/invoices", response_model=ApiResponse)
async def create_invoice(
    body: InvoiceInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建发票草稿;不自动核验、不自动过账。"""
    invoice = FinanceCenterMumarenInvoice(
        book_id=body.book_id,
        invoice_no=body.invoice_no,
        invoice_type=body.invoice_type,
        invoice_date=body.invoice_date,
        counterparty_name=body.counterparty_name,
        amount=body.amount,
        tax_amount=body.tax_amount,
        verification_status="draft",
        workflow_status="draft",
    )
    db.add(invoice)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_invoice",
        operator_id=_actor_id(current_user),
        detail=f"创建发票 {body.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已创建")


@router.put("/invoices/{invoice_id}", response_model=ApiResponse)
async def update_invoice(
    invoice_id: int,
    body: InvoiceUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新发票(仅 draft 可改);强制同账簿校验。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},不可修改")
    for field in ("invoice_type", "invoice_date", "counterparty_name", "amount", "tax_amount"):
        value = getattr(body, field)
        if value is not None:
            setattr(invoice, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=invoice.book_id, action="update_invoice",
        operator_id=_actor_id(current_user),
        detail=f"更新发票 {invoice.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已更新")


@router.delete("/invoices/{invoice_id}", response_model=ApiResponse)
async def delete_invoice(
    invoice_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除发票(仅 draft 可删);强制同账簿校验。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},仅 draft 可删除")
    invoice_no = invoice.invoice_no
    await db.delete(invoice)
    _add_audit_log(
        db, book_id=book_id, action="delete_invoice",
        operator_id=_actor_id(current_user),
        detail=f"删除发票 {invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(message="发票已删除")


@router.post("/invoices/{invoice_id}/verify", response_model=ApiResponse)
async def verify_invoice(
    invoice_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """发票核验:draft → verified;不自动过账。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},无法核验")
    invoice.verification_status = "verified"
    await db.flush()
    _add_audit_log(
        db, book_id=invoice.book_id, action="verify_invoice",
        operator_id=_actor_id(current_user),
        detail=f"核验发票 {invoice.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已核验")


# ===========================================================================
# Task 4: 出纳账户与流水(复用 cash_accounts + cash_flows)
# ===========================================================================

class CashAccountInput(BaseModel):
    book_id: int = Field(ge=1)
    account_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    account_type: str = Field(default="bank", pattern=r"^(bank|cash)$")
    currency: str = Field(default="CNY", max_length=8)


class CashAccountUpdate(BaseModel):
    book_id: int = Field(ge=1)
    account_name: str | None = None
    account_type: str | None = Field(default=None, pattern=r"^(bank|cash)$")
    currency: str | None = None


class CashFlowInput(BaseModel):
    book_id: int = Field(ge=1)
    cash_account_id: int = Field(ge=1)
    flow_date: date
    direction: str = Field(pattern=r"^(in|out)$")
    amount: Decimal = Field(gt=0)
    category: str | None = Field(default=None, max_length=64)
    counterparty_name: str | None = Field(default=None, max_length=128)


def _cash_account_data(account: FinanceCenterMumarenCashAccount) -> dict:
    return {
        "id": account.id,
        "book_id": account.book_id,
        "account_code": account.account_code,
        "account_name": account.account_name,
        "account_type": account.account_type,
        "currency": account.currency,
        "is_active": account.is_active,
    }


def _cash_flow_data(flow: FinanceCenterMumarenCashFlow) -> dict:
    return {
        "id": flow.id,
        "book_id": flow.book_id,
        "cash_account_id": flow.cash_account_id,
        "flow_date": flow.flow_date,
        "direction": flow.direction,
        "amount": flow.amount,
        "category": flow.category,
        "counterparty_name": flow.counterparty_name,
        "workflow_status": flow.workflow_status,
    }


@router.get("/cash-accounts", response_model=ApiResponse)
async def list_cash_accounts(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出出纳账户,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenCashAccount)
        .where(FinanceCenterMumarenCashAccount.book_id == book_id)
        .order_by(FinanceCenterMumarenCashAccount.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_cash_account_data(row) for row in rows])


@router.post("/cash-accounts", response_model=ApiResponse)
async def create_cash_account(
    body: CashAccountInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建出纳账户;不自动审核、不自动过账。"""
    account = FinanceCenterMumarenCashAccount(
        book_id=body.book_id,
        account_code=body.account_code,
        account_name=body.account_name,
        account_type=body.account_type,
        currency=body.currency,
        is_active=True,
    )
    db.add(account)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"创建出纳账户 {body.account_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已创建")


@router.put("/cash-accounts/{account_id}", response_model=ApiResponse)
async def update_cash_account(
    account_id: int,
    body: CashAccountUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新出纳账户;强制同账簿校验。"""
    account = await db.get(FinanceCenterMumarenCashAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {account_id} 不存在")
    if account.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    for field in ("account_name", "account_type", "currency"):
        value = getattr(body, field)
        if value is not None:
            setattr(account, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=account.book_id, action="update_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"更新出纳账户 {account.account_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已更新")


@router.delete("/cash-accounts/{account_id}", response_model=ApiResponse)
async def delete_cash_account(
    account_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除出纳账户:活跃账户软删除置 is_active=false;已停用账户硬删除。"""
    account = await db.get(FinanceCenterMumarenCashAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {account_id} 不存在")
    if account.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    account_code = account.account_code
    if account.is_active:
        account.is_active = False
        await db.flush()
        _add_audit_log(
            db, book_id=book_id, action="delete_cash_account",
            operator_id=_actor_id(current_user),
            detail=f"停用出纳账户 {account_code}",
        )
        await db.flush()
        return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已停用")
    await db.delete(account)
    _add_audit_log(
        db, book_id=book_id, action="delete_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"删除出纳账户 {account_code}",
    )
    await db.flush()
    return ApiResponse.ok(message="出纳账户已删除")


@router.get("/cash-flows", response_model=ApiResponse)
async def list_cash_flows(
    book_id: int = Query(ge=1),
    cash_account_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出资金流水,支持 book_id 与 cash_account_id 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenCashFlow).where(FinanceCenterMumarenCashFlow.book_id == book_id)
    if cash_account_id is not None:
        stmt = stmt.where(FinanceCenterMumarenCashFlow.cash_account_id == cash_account_id)
    stmt = stmt.order_by(FinanceCenterMumarenCashFlow.flow_date.desc(), FinanceCenterMumarenCashFlow.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_cash_flow_data(row) for row in rows])


@router.post("/cash-flows", response_model=ApiResponse)
async def create_cash_flow(
    body: CashFlowInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建资金流水草稿;强制同账簿校验,不自动过账。"""
    account = await db.get(FinanceCenterMumarenCashAccount, body.cash_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {body.cash_account_id} 不存在")
    if account.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="出纳账户与目标账簿不一致,禁止跨账簿写入")
    flow = FinanceCenterMumarenCashFlow(
        book_id=body.book_id,
        cash_account_id=body.cash_account_id,
        flow_date=body.flow_date,
        direction=body.direction,
        amount=body.amount,
        category=body.category,
        counterparty_name=body.counterparty_name,
        workflow_status="draft",
    )
    db.add(flow)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_cash_flow",
        operator_id=_actor_id(current_user),
        detail=f"创建资金流水 {body.direction} {body.amount} 账户 {body.cash_account_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_flow_data(flow), message="资金流水已创建")


# ===========================================================================
# Task 5: 工资 CRUD(复用 payrolls)
# ===========================================================================

class PayrollInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    employee_no: str = Field(min_length=1, max_length=64)
    employee_name: str = Field(min_length=1, max_length=128)
    gross_amount: Decimal = Field(ge=0)
    deduction_amount: Decimal = Field(default=Decimal("0"), ge=0)
    net_amount: Decimal = Field(ge=0)


class PayrollUpdate(BaseModel):
    book_id: int = Field(ge=1)
    employee_name: str | None = None
    gross_amount: Decimal | None = Field(default=None, ge=0)
    deduction_amount: Decimal | None = Field(default=None, ge=0)
    net_amount: Decimal | None = Field(default=None, ge=0)


def _payroll_data(payroll: FinanceCenterMumarenPayroll) -> dict:
    return {
        "id": payroll.id,
        "book_id": payroll.book_id,
        "period": payroll.period,
        "employee_no": payroll.employee_no,
        "employee_name": payroll.employee_name,
        "gross_amount": payroll.gross_amount,
        "deduction_amount": payroll.deduction_amount,
        "net_amount": payroll.net_amount,
        "workflow_status": payroll.workflow_status,
        "voucher_id": payroll.voucher_id,
    }


@router.get("/payrolls", response_model=ApiResponse)
async def list_payrolls(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出工资,支持 book_id 与 period 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenPayroll).where(FinanceCenterMumarenPayroll.book_id == book_id)
    if period is not None:
        stmt = stmt.where(FinanceCenterMumarenPayroll.period == period)
    stmt = stmt.order_by(FinanceCenterMumarenPayroll.period.desc(), FinanceCenterMumarenPayroll.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_payroll_data(row) for row in rows])


@router.post("/payrolls", response_model=ApiResponse)
async def create_payroll(
    body: PayrollInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建工资草稿;不自动发放、不自动过账。"""
    payroll = FinanceCenterMumarenPayroll(
        book_id=body.book_id,
        period=body.period,
        employee_no=body.employee_no,
        employee_name=body.employee_name,
        gross_amount=body.gross_amount,
        deduction_amount=body.deduction_amount,
        net_amount=body.net_amount,
        workflow_status="draft",
    )
    db.add(payroll)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_payroll",
        operator_id=_actor_id(current_user),
        detail=f"创建工资 {body.period} {body.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已创建")


@router.put("/payrolls/{payroll_id}", response_model=ApiResponse)
async def update_payroll(
    payroll_id: int,
    body: PayrollUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新工资(仅 draft 可改);强制同账簿校验。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},不可修改")
    for field in ("employee_name", "gross_amount", "deduction_amount", "net_amount"):
        value = getattr(body, field)
        if value is not None:
            setattr(payroll, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=payroll.book_id, action="update_payroll",
        operator_id=_actor_id(current_user),
        detail=f"更新工资 {payroll.period} {payroll.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已更新")


@router.delete("/payrolls/{payroll_id}", response_model=ApiResponse)
async def delete_payroll(
    payroll_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除工资(仅 draft 可删);强制同账簿校验。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},仅 draft 可删除")
    desc = f"{payroll.period} {payroll.employee_no}"
    await db.delete(payroll)
    _add_audit_log(
        db, book_id=book_id, action="delete_payroll",
        operator_id=_actor_id(current_user),
        detail=f"删除工资 {desc}",
    )
    await db.flush()
    return ApiResponse.ok(message="工资已删除")


@router.post("/payrolls/{payroll_id}/pay", response_model=ApiResponse)
async def pay_payroll(
    payroll_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """工资发放:draft → paid(workflow_status);不自动过账。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},无法发放")
    payroll.workflow_status = "paid"
    await db.flush()
    _add_audit_log(
        db, book_id=payroll.book_id, action="pay_payroll",
        operator_id=_actor_id(current_user),
        detail=f"发放工资 {payroll.period} {payroll.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已发放")


# ===========================================================================
# Task 6: 结账(复用 fiscal_periods)
# ===========================================================================

def _fiscal_period_data(period: FinanceCenterMumarenFiscalPeriod) -> dict:
    return {
        "id": period.id,
        "book_id": period.book_id,
        "period_code": period.period_code,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "status": period.status,
        "closed_by": period.closed_by,
        "closed_at": period.closed_at,
    }


@router.get("/periods", response_model=ApiResponse)
async def list_fiscal_periods(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出会计期间,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenFiscalPeriod)
        .where(FinanceCenterMumarenFiscalPeriod.book_id == book_id)
        .order_by(FinanceCenterMumarenFiscalPeriod.period_code.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_fiscal_period_data(row) for row in rows])


@router.post("/periods/{period_id}/close", response_model=ApiResponse)
async def close_fiscal_period(
    period_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """结账:open → closed,记录 closed_by/closed_at。

    预检:本期所有凭证必须 posted、试算平衡、无未审核记录。
    """
    period = await db.get(FinanceCenterMumarenFiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail=f"会计期间 {period_id} 不存在")
    if period.status != "open":
        raise HTTPException(status_code=409, detail=f"当前状态 {period.status},无法结账")

    not_posted_count = int((await db.execute(
        select(func.count(FinanceCenterMumarenVoucher.id)).where(
            FinanceCenterMumarenVoucher.book_id == period.book_id,
            FinanceCenterMumarenVoucher.voucher_date >= period.start_date,
            FinanceCenterMumarenVoucher.voucher_date <= period.end_date,
            FinanceCenterMumarenVoucher.status != "posted",
        )
    )).scalar_one())
    if not_posted_count > 0:
        raise HTTPException(status_code=409, detail=f"本期存在 {not_posted_count} 张未过账凭证,禁止结账")

    totals = (await db.execute(
        select(
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_debit), 0),
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_credit), 0),
        ).where(
            FinanceCenterMumarenVoucher.book_id == period.book_id,
            FinanceCenterMumarenVoucher.voucher_date >= period.start_date,
            FinanceCenterMumarenVoucher.voucher_date <= period.end_date,
        )
    )).one()
    total_debit, total_credit = Decimal(totals[0]), Decimal(totals[1])
    if total_debit != total_credit:
        raise HTTPException(
            status_code=409,
            detail=f"试算不平衡:借方 {total_debit} ≠ 贷方 {total_credit},禁止结账",
        )

    period.status = "closed"
    period.closed_by = _actor_id(current_user)
    period.closed_at = datetime.now(timezone.utc)
    await db.flush()
    _add_audit_log(
        db, book_id=period.book_id, action="close_period",
        operator_id=_actor_id(current_user),
        detail=f"结账期间 {period.period_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fiscal_period_data(period), message="会计期间已结账")


@router.post("/periods/{period_id}/reopen", response_model=ApiResponse)
async def reopen_fiscal_period(
    period_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """反结账:closed → open(需 admin 权限)。"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="反结账需要管理员权限")
    period = await db.get(FinanceCenterMumarenFiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail=f"会计期间 {period_id} 不存在")
    if period.status != "closed":
        raise HTTPException(status_code=409, detail=f"当前状态 {period.status},仅 closed 可反结账")
    period.status = "open"
    period.closed_by = None
    period.closed_at = None
    await db.flush()
    _add_audit_log(
        db, book_id=period.book_id, action="reopen_period",
        operator_id=_actor_id(current_user),
        detail=f"反结账期间 {period.period_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fiscal_period_data(period), message="会计期间已反结账")


# ===========================================================================
# Task 7: 应收应付补充(复用 receivable_orders + payable_orders)
# ===========================================================================

class ArApOrderUpdate(BaseModel):
    book_id: int = Field(ge=1)
    order_date: date | None = None
    counterparty_name: str | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=500)


_AR_AP_MODELS = {
    "receivable": FinanceCenterMumarenReceivableOrder,
    "payable": FinanceCenterMumarenPayableOrder,
}


@router.get("/ar-ap/orders", response_model=ApiResponse)
async def list_ar_ap_orders(
    book_id: int = Query(ge=1),
    order_type: str = Query(default="receivable", pattern=r"^(receivable|payable)$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出租收应付单据,支持 book_id 与 order_type 过滤,默认 limit 100,最大 500。"""
    model = _AR_AP_MODELS[order_type]
    rows = list((await db.execute(
        select(model)
        .where(model.book_id == book_id)
        .order_by(model.order_date.desc(), model.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_order_data(row) for row in rows])


@router.put("/ar-ap/orders/{order_id}", response_model=ApiResponse)
async def update_ar_ap_order(
    order_id: int,
    body: ArApOrderUpdate,
    order_type: str = Query(pattern=r"^(receivable|payable)$"),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """编辑 AR/AP 单据(仅 draft 可改);强制同账簿校验。"""
    model = _AR_AP_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"{order_type} 单据 {order_id} 不存在")
    if order.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if order.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {order.workflow_status},仅 draft 可修改")
    if body.total_amount is not None and Decimal(body.total_amount) < Decimal(order.settled_amount or 0):
        raise HTTPException(status_code=400, detail="总金额不能小于已结算金额")
    if body.order_date is not None:
        order.order_date = body.order_date
        order.period = _period_code_from_date(body.order_date)
    if body.counterparty_name is not None:
        order.counterparty_name = body.counterparty_name
    if body.total_amount is not None:
        order.total_amount = body.total_amount
    if body.remark is not None:
        order.remark = body.remark
    await db.flush()
    action = f"update_{order_type}_order"
    _add_audit_log(
        db, book_id=order.book_id, action=action,
        operator_id=_actor_id(current_user),
        detail=f"编辑 {order_type} 单据 {order.order_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已更新")


@router.delete("/ar-ap/orders/{order_id}", response_model=ApiResponse)
async def delete_ar_ap_order(
    order_id: int,
    order_type: str = Query(pattern=r"^(receivable|payable)$"),
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除 AR/AP 单据(仅 draft 可删);强制同账簿校验。"""
    model = _AR_AP_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"{order_type} 单据 {order_id} 不存在")
    if order.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if order.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {order.workflow_status},仅 draft 可删除")
    order_no = order.order_no
    await db.delete(order)
    action = f"delete_{order_type}_order"
    _add_audit_log(
        db, book_id=book_id, action=action,
        operator_id=_actor_id(current_user),
        detail=f"删除 {order_type} 单据 {order_no}",
    )
    await db.flush()
    return ApiResponse.ok(message="AR/AP 单据已删除")


# ===========================================================================
# Task 8: 操作日志查询(复用 audit_logs)
# ===========================================================================

def _audit_log_data(log: FinanceCenterMumarenAuditLog) -> dict:
    return {
        "id": log.id,
        "book_id": log.book_id,
        "voucher_id": log.voucher_id,
        "action": log.action,
        "operator_id": log.operator_id,
        "detail": log.detail,
        "created_at": log.created_at,
    }


@router.get("/audit-logs", response_model=ApiResponse)
async def list_audit_logs(
    book_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=64),
    operator_id: int | None = Query(default=None, ge=1),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """查询审计日志,支持 book_id/action/operator_id/日期范围过滤,按 created_at DESC 排序。"""
    conditions = []
    if book_id is not None:
        conditions.append(FinanceCenterMumarenAuditLog.book_id == book_id)
    if action is not None:
        conditions.append(FinanceCenterMumarenAuditLog.action == action)
    if operator_id is not None:
        conditions.append(FinanceCenterMumarenAuditLog.operator_id == operator_id)
    if start_date is not None:
        conditions.append(FinanceCenterMumarenAuditLog.created_at >= start_date)
    if end_date is not None:
        conditions.append(FinanceCenterMumarenAuditLog.created_at < end_date)
    stmt = select(FinanceCenterMumarenAuditLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(FinanceCenterMumarenAuditLog.created_at.desc(), FinanceCenterMumarenAuditLog.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_audit_log_data(row) for row in rows])
