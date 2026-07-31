"""Independent Mumaren AR/AP and tax read/write APIs.

These endpoints operate only on the isolated ``finance_center_mumaren`` schema.
They do not create vouchers and never call the legacy Huabang finance routers.
The write path follows the fixed "draft → finance review → manual settle/pay"
flow and never auto-generates or posts accounting entries.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mumaren_finance_center import (
    require_mumaren_finance_access,
    require_mumaren_voucher_post,
    require_mumaren_voucher_review,
    require_mumaren_voucher_write,
)
from app.core.database import get_db
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)
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
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 草稿已创建")


@router.post("/ar-ap/orders/{order_id}/review", response_model=ApiResponse)
async def review_ar_ap_order_endpoint(
    order_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    """财务审核 AR/AP 草稿;仅 draft → reviewed,不产生凭证分录。"""
    try:
        order = await _review_ar_ap_with_fallback(db, order_id=order_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已审核")


@router.post("/ar-ap/orders/{order_id}/settle", response_model=ApiResponse)
async def settle_ar_ap_order_endpoint(
    order_id: int,
    body: ArApSettleInput,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """人工结算 AR/AP 单据;防超额,不产生凭证分录。"""
    try:
        order = await _settle_ar_ap_with_fallback(
            db, order_id=order_id,
            settlement_date=body.settlement_date, amount=body.amount,
            operator_id=_actor_id(current_user), remark=body.remark,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
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
    return ApiResponse.ok(data=_tax_record_data(record), message="税务单据已缴税")
