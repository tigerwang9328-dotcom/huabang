"""Independent Mumaren AR/AP and tax read APIs.

These endpoints read only the isolated ``finance_center_mumaren`` schema.  They
do not create vouchers and never call the legacy Huabang finance routers.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mumaren_finance_center import require_mumaren_finance_access
from app.core.database import get_db
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.mumaren_finance_center.ar_ap import build_aging
from app.services.mumaren_finance_center.tax import build_tax_alerts, tax_record_balance


router = APIRouter(prefix="/finance-center/mumaren", tags=["牧马人财务中心：往来与税务"])


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
