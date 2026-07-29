"""Finance V2.0 API kept separate from legacy write paths until cutover."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.finance_v2 import (
    FinanceV2AccountVersion,
    FinanceV2AccountingBook,
    FinanceV2FiscalPeriod,
    FinanceV2Voucher,
)
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
    command_id: str = Field(min_length=1, max_length=128)
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


@router.get("/books/{book_id}/write-readiness", response_model=ApiResponse)
async def get_book_write_readiness(
    book_id: int,
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
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
    role = _finance_gate_role(current_user)
    readiness = {}
    for command in ("draft", "review", "post"):
        try:
            assert_command_enabled(
                gates,
                command=command,
                environment=settings.APP_ENV,
                book=str(book_id),
                role=role,
            )
        except FeatureGateError as error:
            readiness[command] = {"enabled": False, "reason": str(error)}
        else:
            readiness[command] = {"enabled": True, "reason": None}
    return ApiResponse.ok(data={"book_id": book_id, "role": role, "commands": readiness})


@router.get("/books/{book_id}/periods", response_model=ApiResponse)
async def list_book_periods(
    book_id: int,
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(FinanceV2FiscalPeriod)
            .where(FinanceV2FiscalPeriod.book_id == book_id)
            .order_by(FinanceV2FiscalPeriod.start_date.desc())
        )
    ).scalars().all()
    return ApiResponse.ok(
        data=[
            {
                "id": row.id,
                "period_code": row.period_code,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "status": row.status,
                "version": row.version,
            }
            for row in rows
        ]
    )


@router.get("/books/{book_id}/accounts", response_model=ApiResponse)
async def list_book_accounts(
    book_id: int,
    active_on: date | None = Query(default=None),
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    statement = (
        select(FinanceV2AccountVersion)
        .where(
            FinanceV2AccountVersion.book_id == book_id,
            FinanceV2AccountVersion.is_postable.is_(True),
        )
        .order_by(FinanceV2AccountVersion.account_code)
    )
    if active_on:
        statement = statement.where(
            FinanceV2AccountVersion.effective_from <= active_on,
            or_(
                FinanceV2AccountVersion.effective_to.is_(None),
                FinanceV2AccountVersion.effective_to >= active_on,
            ),
        )
    rows = (await db.execute(statement)).scalars().all()
    return ApiResponse.ok(
        data=[
            {
                "id": row.id,
                "account_code": row.account_code,
                "account_name": row.account_name,
                "normal_balance": row.normal_balance,
                "effective_from": row.effective_from,
                "effective_to": row.effective_to,
            }
            for row in rows
        ]
    )


@router.get("/vouchers", response_model=ApiResponse)
async def list_vouchers(
    book_id: int,
    period_id: int | None = Query(default=None),
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: SysUser = Depends(require_roles("finance_manager")),
    db: AsyncSession = Depends(get_db),
):
    statement = select(FinanceV2Voucher).where(FinanceV2Voucher.book_id == book_id)
    if period_id is not None:
        statement = statement.where(FinanceV2Voucher.period_id == period_id)
    if status is not None:
        statement = statement.where(FinanceV2Voucher.status == status)
    rows = (
        await db.execute(
            statement.order_by(FinanceV2Voucher.voucher_date.desc(), FinanceV2Voucher.id.desc()).limit(limit)
        )
    ).scalars().all()
    return ApiResponse.ok(
        data=[
            {
                "id": row.id,
                "period_id": row.period_id,
                "voucher_no": row.voucher_no,
                "voucher_group": row.voucher_group,
                "voucher_date": row.voucher_date,
                "status": row.status,
                "version": row.version,
                "total_debit": row.total_debit,
                "total_credit": row.total_credit,
                "prepared_by": row.prepared_by,
                "reviewer_id": row.reviewer_id,
                "approved_by": row.approved_by,
                "posted_by": row.posted_by,
            }
            for row in rows
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
    workflow = FinanceV2VoucherWorkflow(db)
    try:
        result = await workflow.command(
            voucher_id=voucher_id,
            action=body.action,
            actor_id=_actor(current_user),
            expected_version=body.expected_version,
            reason=body.reason,
            command_id=body.command_id,
        )
        if body.action == "post":
            attempt_id = result.get("posting_attempt_id")
            if attempt_id is None:
                raise RuntimeError("posted voucher result is missing posting_attempt_id")
            try:
                await db.commit()
            except Exception as error:
                await db.rollback()
                await workflow.mark_posting_attempt_failed(attempt_id, error)
                raise
            await workflow.mark_posting_attempt_succeeded(attempt_id)
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result, message="V2 凭证命令已执行")
