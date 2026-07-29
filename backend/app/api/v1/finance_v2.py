"""Finance V2.0 API kept separate from legacy write paths until cutover."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.finance_v2_deps import require_finance_v2_permission
from app.core.config import settings
from app.core.database import get_finance_db
from app.models.finance_v2 import (
    FinanceV2AccountVersion,
    FinanceV2AccountingBook,
    FinanceV2FiscalPeriod,
    FinanceV2LedgerBalance,
    FinanceV2OperationEvent,
    FinanceV2Voucher,
    FinanceV2VoucherLine,
)
from app.models.finance_v2_operations import FinanceV2FeatureGate
from app.models.finance_v2_operations import FinanceV2PostingAttempt
from app.models.finance_v2_period_close import FinanceV2PeriodCloseBatch
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.finance_v2.domain import FinanceV2DomainError
from app.services.finance_v2.feature_gate_domain import FeatureGateError, GateScope, assert_command_enabled
from app.services.finance_v2.finance_observability import monitoring_payload
from app.services.finance_v2.opening_balance_domain import OpeningBalanceError
from app.services.finance_v2.opening_balance_service import FinanceV2OpeningBalanceService
from app.services.finance_v2.period_close_workflow import FinanceV2PeriodCloseWorkflow
from app.services.finance_v2.voucher_workflow import FinanceV2VoucherWorkflow
from app.services.finance_v2.platform_permissions import (
    FINANCE_V2_READ_PERMISSION,
    FINANCE_V2_WRITE_PERMISSION,
)


router = APIRouter(prefix="/finance-center/v2", tags=["财务中心 V2.0"])
require_finance_v2_read = require_finance_v2_permission(FINANCE_V2_READ_PERMISSION)
require_finance_v2_write = require_finance_v2_permission(FINANCE_V2_WRITE_PERMISSION)


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


class VoucherDraftUpdateInput(BaseModel):
    voucher_date: date
    entries: list[VoucherLineInput] = Field(default_factory=list)
    command_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)


class PeriodCommandInput(BaseModel):
    action: str = Field(pattern=r"^(register_profit_closing|start_close|complete_close|request_reopen|approve_reopen)$")
    command_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
    voucher_id: int | None = Field(default=None, ge=1)


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
    try:
        await FinanceV2OpeningBalanceService(db).assert_current_writes_allowed(book_id=book_id)
    except OpeningBalanceError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/books", response_model=ApiResponse)
async def list_books(
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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
    try:
        await FinanceV2OpeningBalanceService(db).assert_current_writes_allowed(book_id=book_id)
    except OpeningBalanceError as error:
        opening_balance_reason = str(error)
    else:
        opening_balance_reason = None
    readiness = {}
    for command in ("draft", "review", "post", "period_close"):
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
            readiness[command] = {
                "enabled": opening_balance_reason is None,
                "reason": opening_balance_reason,
            }
    return ApiResponse.ok(data={"book_id": book_id, "role": role, "commands": readiness})


@router.get("/books/{book_id}/periods", response_model=ApiResponse)
async def list_book_periods(
    book_id: int,
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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


@router.get("/books/{book_id}/periods/{period_id}/close-readiness", response_model=ApiResponse)
async def get_period_close_readiness(
    book_id: int,
    period_id: int,
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    try:
        result = await FinanceV2PeriodCloseWorkflow(db).readiness(book_id=book_id, period_id=period_id)
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result)


@router.post("/books/{book_id}/periods/{period_id}/commands", response_model=ApiResponse)
async def execute_period_command(
    book_id: int,
    period_id: int,
    body: PeriodCommandInput,
    current_user: SysUser = Depends(require_finance_v2_write),
    db: AsyncSession = Depends(get_finance_db),
):
    await _assert_v2_write_enabled(
        db,
        command="period_close",
        book_id=book_id,
        role=_finance_gate_role(current_user),
    )
    try:
        result = await FinanceV2PeriodCloseWorkflow(db).command(
            book_id=book_id,
            period_id=period_id,
            action=body.action,
            actor_id=_actor(current_user),
            expected_version=body.expected_version,
            command_id=body.command_id,
            reason=body.reason,
            voucher_id=body.voucher_id,
        )
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result, message="V2 会计期间命令已执行")


@router.get("/books/{book_id}/periods/{period_id}/trial-balance", response_model=ApiResponse)
async def get_trial_balance(
    book_id: int,
    period_id: int,
    limit: int = Query(default=500, ge=1, le=1000),
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    book = await db.get(FinanceV2AccountingBook, book_id)
    period = await db.get(FinanceV2FiscalPeriod, period_id)
    if not book or not period or period.book_id != book_id:
        raise HTTPException(status_code=404, detail="V2 accounting book or fiscal period not found")
    rows = (
        await db.execute(
            select(FinanceV2LedgerBalance, FinanceV2AccountVersion)
            .join(FinanceV2AccountVersion, FinanceV2AccountVersion.id == FinanceV2LedgerBalance.account_version_id)
            .where(
                FinanceV2LedgerBalance.book_id == book_id,
                FinanceV2LedgerBalance.period_id == period_id,
            )
            .order_by(FinanceV2AccountVersion.account_code, FinanceV2LedgerBalance.dimension_set_id)
            .limit(limit)
        )
    ).all()
    return ApiResponse.ok(
        data={
            "book_id": book_id,
            "period_id": period_id,
            "period_code": period.period_code,
            "formal_report_status": "blocked" if book.formal_report_blocked else "pending_mapping",
            "formal_report_message": "当前仅提供 V2 当前账试算表；资产负债表和利润表须在科目映射经核对后另行发布。",
            "rows": [
                {
                    "account_version_id": balance.account_version_id,
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "dimension_set_id": balance.dimension_set_id,
                    "currency_code": balance.currency_code,
                    "opening_debit": balance.opening_debit,
                    "opening_credit": balance.opening_credit,
                    "period_debit": balance.period_debit,
                    "period_credit": balance.period_credit,
                    "closing_debit": balance.closing_debit,
                    "closing_credit": balance.closing_credit,
                }
                for balance, account in rows
            ],
        }
    )


@router.get("/books/{book_id}/periods/{period_id}/ledger-lines", response_model=ApiResponse)
async def list_ledger_lines(
    book_id: int,
    period_id: int,
    account_version_id: int | None = Query(default=None),
    after_line_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    period = await db.get(FinanceV2FiscalPeriod, period_id)
    if not period or period.book_id != book_id:
        raise HTTPException(status_code=404, detail="V2 fiscal period not found")
    statement = (
        select(FinanceV2VoucherLine, FinanceV2Voucher, FinanceV2AccountVersion)
        .join(FinanceV2Voucher, FinanceV2Voucher.id == FinanceV2VoucherLine.voucher_id)
        .join(FinanceV2AccountVersion, FinanceV2AccountVersion.id == FinanceV2VoucherLine.account_version_id)
        .where(
            FinanceV2Voucher.book_id == book_id,
            FinanceV2Voucher.period_id == period_id,
            FinanceV2Voucher.status == "posted",
        )
        .order_by(FinanceV2VoucherLine.id)
        .limit(limit + 1)
    )
    if account_version_id is not None:
        statement = statement.where(FinanceV2VoucherLine.account_version_id == account_version_id)
    if after_line_id is not None:
        statement = statement.where(FinanceV2VoucherLine.id > after_line_id)
    rows = (await db.execute(statement)).all()
    page = rows[:limit]
    return ApiResponse.ok(
        data={
            "lines": [
                {
                    "line_id": line.id,
                    "voucher_id": voucher.id,
                    "voucher_no": voucher.voucher_no,
                    "voucher_group": voucher.voucher_group,
                    "voucher_date": voucher.voucher_date,
                    "line_no": line.line_no,
                    "account_version_id": account.id,
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "dimension_set_id": line.dimension_set_id,
                    "summary": line.summary,
                    "currency_code": line.currency_code,
                    "exchange_rate": line.exchange_rate,
                    "debit_amount": line.debit_amount,
                    "credit_amount": line.credit_amount,
                }
                for line, voucher, account in page
            ],
            "next_after_line_id": page[-1][0].id if len(rows) > limit else None,
        }
    )


@router.get("/monitoring/summary", response_model=ApiResponse)
async def get_monitoring_summary(
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    async def count_rows(model, *conditions) -> int:
        return int((await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())

    failed_posts = await count_rows(FinanceV2PostingAttempt, FinanceV2PostingAttempt.status == "failed")
    history_conflicts = int(
        (
            await db.execute(
                text("SELECT count(*) FROM fin_read.history_import_batch WHERE status = 'conflicted'")
            )
        ).scalar_one()
    )
    failed_closes = await count_rows(FinanceV2PeriodCloseBatch, FinanceV2PeriodCloseBatch.status == "failed")
    gates = (await db.execute(select(FinanceV2FeatureGate).order_by(FinanceV2FeatureGate.id.desc()))).scalars().all()
    metric_values = {
        "posting_attempt_failed": failed_posts,
        "history_import_conflicted": history_conflicts,
        "period_close_failed": failed_closes,
    }
    metric_policies = monitoring_payload(metric_values)
    return ApiResponse.ok(
        data={
            "metrics": metric_values,
            "metric_policies": metric_policies,
            "gates": [
                {
                    "scope_type": gate.scope_type,
                    "scope_key": gate.scope_key,
                    "gate_name": gate.gate_name,
                    "enabled": gate.enabled,
                    "effective_at": gate.effective_at,
                }
                for gate in gates
            ],
            "unavailable_metrics": [
                item["metric_key"]
                for item in metric_policies
                if item["availability"] == "unavailable"
            ],
            "message": "仅返回已持久化的 V2 运营指标；未接入指标采集器的项目明确标为不可用，不能当作零。",
        }
    )
@router.get("/books/{book_id}/accounts", response_model=ApiResponse)
async def list_book_accounts(
    book_id: int,
    active_on: date | None = Query(default=None),
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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


@router.get("/vouchers/{voucher_id}", response_model=ApiResponse)
async def get_voucher_detail(
    voucher_id: int,
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    voucher = await db.get(FinanceV2Voucher, voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="V2 voucher not found")
    lines = (
        await db.execute(
            select(FinanceV2VoucherLine)
            .where(FinanceV2VoucherLine.voucher_id == voucher_id)
            .order_by(FinanceV2VoucherLine.line_no, FinanceV2VoucherLine.id)
        )
    ).scalars().all()
    events = (
        await db.execute(
            select(FinanceV2OperationEvent)
            .where(FinanceV2OperationEvent.voucher_id == voucher_id)
            .order_by(FinanceV2OperationEvent.created_at, FinanceV2OperationEvent.id)
        )
    ).scalars().all()
    return ApiResponse.ok(
        data={
            "id": voucher.id,
            "book_id": voucher.book_id,
            "period_id": voucher.period_id,
            "voucher_no": voucher.voucher_no,
            "voucher_group": voucher.voucher_group,
            "voucher_date": voucher.voucher_date,
            "status": voucher.status,
            "version": voucher.version,
            "total_debit": voucher.total_debit,
            "total_credit": voucher.total_credit,
            "prepared_by": voucher.prepared_by,
            "reviewer_id": voucher.reviewer_id,
            "approved_by": voucher.approved_by,
            "posted_by": voucher.posted_by,
            "source_system": voucher.source_system,
            "lines": [
                {
                    "id": line.id,
                    "line_no": line.line_no,
                    "account_version_id": line.account_version_id,
                    "dimension_set_id": line.dimension_set_id,
                    "summary": line.summary,
                    "currency_code": line.currency_code,
                    "exchange_rate": line.exchange_rate,
                    "debit_amount": line.debit_amount,
                    "credit_amount": line.credit_amount,
                }
                for line in lines
            ],
            "operation_events": [
                {
                    "id": event.id,
                    "action": event.action,
                    "actor_id": event.actor_id,
                    "reason": event.reason,
                    "command_id": event.command_id,
                    "before_data": event.before_data,
                    "after_data": event.after_data,
                    "created_at": event.created_at,
                }
                for event in events
            ],
        }
    )


@router.get("/history/vouchers", response_model=ApiResponse)
async def list_history_vouchers(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
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


@router.get("/history/vouchers/{voucher_id}/lines", response_model=ApiResponse)
async def list_history_voucher_lines(
    voucher_id: int,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: SysUser = Depends(require_finance_v2_read),
    db: AsyncSession = Depends(get_finance_db),
):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, voucher_id, line_no, line_source_pk, account_code, summary,
                       currency_code, exchange_rate, debit_amount, credit_amount, raw_dimensions,
                       source_system, source_database, voucher_no, voucher_date,
                       fiscal_year, fiscal_period, historical_marker
                FROM fin_read.history_voucher_line
                WHERE voucher_id = :voucher_id
                ORDER BY line_no, id
                LIMIT :limit
                """
            ),
            {"voucher_id": voucher_id, "limit": limit},
        )
    ).mappings().all()
    return ApiResponse.ok(data=[dict(row) for row in rows])


@router.post("/vouchers", response_model=ApiResponse)
async def create_voucher_draft(
    body: VoucherDraftInput,
    current_user: SysUser = Depends(require_finance_v2_write),
    db: AsyncSession = Depends(get_finance_db),
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


@router.put("/vouchers/{voucher_id}", response_model=ApiResponse)
async def update_voucher_draft(
    voucher_id: int,
    body: VoucherDraftUpdateInput,
    current_user: SysUser = Depends(require_finance_v2_write),
    db: AsyncSession = Depends(get_finance_db),
):
    voucher = await db.get(FinanceV2Voucher, voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="V2 voucher not found")
    await _assert_v2_write_enabled(
        db,
        command="draft",
        book_id=voucher.book_id,
        role=_finance_gate_role(current_user),
    )
    try:
        result = await FinanceV2VoucherWorkflow(db).update_draft(
            voucher_id=voucher_id,
            voucher_date=body.voucher_date,
            entries=[entry.model_dump() for entry in body.entries],
            actor_id=_actor(current_user),
            expected_version=body.expected_version,
            command_id=body.command_id,
        )
    except FinanceV2DomainError as error:
        raise _domain_error(error) from error
    return ApiResponse.ok(data=result, message="V2 凭证草稿已更新")


@router.post("/vouchers/{voucher_id}/commands", response_model=ApiResponse)
async def execute_voucher_command(
    voucher_id: int,
    body: VoucherCommandInput,
    current_user: SysUser = Depends(require_finance_v2_write),
    db: AsyncSession = Depends(get_finance_db),
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
