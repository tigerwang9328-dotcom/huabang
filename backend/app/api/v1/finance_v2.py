"""Finance V2.0 API kept separate from legacy write paths until cutover."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.finance_v2 import FinanceV2AccountingBook, FinanceV2Voucher
from app.models.finance_v2_operations import FinanceV2FeatureGate
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.finance_v2.domain import FinanceV2DomainError
from app.services.finance_v2.feature_gate_domain import FeatureGateError, GateScope, assert_command_enabled
from app.services.finance_v2.voucher_workflow import FinanceV2VoucherWorkflow


router = APIRouter(prefix="/finance-center/v2", tags=["财务中心 V2.0"])


class VoucherLineInput(BaseModel):
    account_version_id: int | None = None
    dimension_set_id: int | None = None
    summary: str = Field(default="", max_length=512)
    currency_code: str = Field(default="CNY", min_length=1, max_length=16)
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0)
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0)


class VoucherDraftInput(BaseModel):
    book_id: int
    period_id: int
    voucher_date: date
    request_id: str = Field(min_length=1, max_length=128)
    entries: list[VoucherLineInput] = Field(default_factory=list)


class VoucherCommandInput(BaseModel):
    action: str = Field(pattern=r"^(submit|start_review|approve|reject|reopen|withdraw|cancel|post)$")
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


def _actor(user: SysUser) -> str:
    return str(getattr(user, "username", None) or getattr(user, "name", None) or user.id)


def _domain_error(error: FinanceV2DomainError) -> HTTPException:
    message = str(error)
    return HTTPException(status_code=409 if "conflict" in message else 400, detail=message)


def _gate_command_for_voucher_action(action: str) -> str:
    if action == "post":
        return "post"
    if action in {"start_review", "approve", "reject"}:
        return "review"
    return "draft"


def _finance_gate_role(user: SysUser) -> str:
    return "super_admin" if getattr(user, "is_admin", False) else "finance_manager"


async def _assert_v2_write_enabled(db: AsyncSession, *, command: str, book_id: int, role: str) -> None:
    rows = (await db.execute(select(FinanceV2FeatureGate))).scalars().all()
    gates = [
        GateScope(
            scope_type=row.scope_type,
            scope_key=row.scope_key,
            gate_name=row.gate_name,
            enabled=row.enabled,
        )
        for row in rows
    ]
    try:
        assert_command_enabled(
            gates,
            command=command,
            environment=settings.APP_ENV,
            book=str(book_id),
            role=role,
        )
    except FeatureGateError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/books", response_model=ApiResponse)
async def list_books(
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    books = (await db.execute(select(FinanceV2AccountingBook).order_by(FinanceV2AccountingBook.book_code))).scalars().all()
    return ApiResponse.ok(
        data=[
            {
                "id": row.id,
                "book_code": row.book_code,
                "book_name": row.book_name,
                "status": row.status,
                "formal_report_blocked": row.formal_report_blocked,
            }
            for row in books
        ]
    )


@router.get("/history/vouchers", response_model=ApiResponse)
async def list_history_vouchers(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, voucher_no, voucher_group, voucher_date, fiscal_year, fiscal_period,
                       total_debit, total_credit, source_system, source_database, historical_marker
                FROM fin_read.history_voucher
                ORDER BY voucher_date DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return ApiResponse.ok(data=[dict(row) for row in rows])


@router.post("/vouchers", response_model=ApiResponse)
async def create_voucher_draft(
    body: VoucherDraftInput,
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_v2_write_enabled(
        db,
        command="draft",
        book_id=body.book_id,
        role=_finance_gate_role(current_user),
    )
    try:
        result = await FinanceV2VoucherWorkflow(db).create_draft(
            book_id=body.book_id,
            period_id=body.period_id,
            voucher_date=body.voucher_date,
            prepared_by=_actor(current_user),
            request_id=body.request_id,
            entries=[entry.model_dump() for entry in body.entries],
        )
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result, message="V2 凭证草稿已保存")


@router.post("/vouchers/{voucher_id}/commands", response_model=ApiResponse)
async def execute_voucher_command(
    voucher_id: int,
    body: VoucherCommandInput,
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    voucher = await db.get(FinanceV2Voucher, voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="V2 voucher not found")
    await _assert_v2_write_enabled(
        db,
        command=_gate_command_for_voucher_action(body.action),
        book_id=voucher.book_id,
        role=_finance_gate_role(current_user),
    )
    try:
        result = await FinanceV2VoucherWorkflow(db).command(
            voucher_id=voucher_id,
            action=body.action,
            actor_id=_actor(current_user),
            expected_version=body.expected_version,
            reason=body.reason,
        )
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result, message="V2 凭证命令已执行")
