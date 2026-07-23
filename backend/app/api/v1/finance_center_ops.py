"""Finance-center operational API: auxiliary, ledger, AR/AP, cashier, assets, invoices, payroll, tax, auto-entry."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.finance_center_ops_service import FinanceCenterOpsService, _actor_name

router = APIRouter(prefix="/finance-center", tags=["正式财务中心-运营"])


# --------------------------------------------------------------------------- #
# Request models                                                               #
# --------------------------------------------------------------------------- #

class AuxCategoryPayload(BaseModel):
    book_id: int
    category_code: str = Field(min_length=1, max_length=64)
    category_name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="active")


class AuxItemPayload(BaseModel):
    book_id: int
    category_id: int
    item_code: str = Field(min_length=1, max_length=128)
    item_name: str = Field(min_length=1, max_length=256)
    target_type: str | None = None
    target_code: str | None = None


class CashAccountPayload(BaseModel):
    book_id: int
    account_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    account_type: str
    ledger_account_id: int
    bank_name: str | None = None
    bank_account_masked: str | None = None
    currency_code: str = "CNY"


class BankTransactionPayload(BaseModel):
    book_id: int
    cash_account_id: int
    transaction_date: date
    amount: Decimal = Field(gt=0)
    direction: Literal["in", "out"]
    counterparty_name: str | None = None
    reference_no: str | None = None
    summary: str | None = None
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class ReconciliationPayload(BaseModel):
    book_id: int
    cash_account_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    statement_balance: Decimal
    ledger_balance: Decimal
    matched_transaction_ids: list[int] = Field(default_factory=list)


class ReceivablePayload(BaseModel):
    book_id: int
    document_no: str = Field(min_length=1, max_length=128)
    counterparty_aux_id: int
    business_date: date
    due_date: date | None = None
    original_amount: Decimal = Field(gt=0)
    currency_code: str = "CNY"
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class PayablePayload(BaseModel):
    book_id: int
    document_no: str = Field(min_length=1, max_length=128)
    counterparty_aux_id: int
    business_date: date
    due_date: date | None = None
    original_amount: Decimal = Field(gt=0)
    currency_code: str = "CNY"
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class SettlementPayload(BaseModel):
    book_id: int
    settlement_type: str = Field(min_length=1, max_length=16)
    receivable_id: int | None = None
    payable_id: int | None = None
    settlement_date: date
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class FixedAssetPayload(BaseModel):
    book_id: int
    asset_code: str = Field(min_length=1, max_length=64)
    asset_name: str = Field(min_length=1, max_length=256)
    category: str = Field(min_length=1, max_length=64)
    acquisition_date: date
    in_service_date: date
    original_cost: Decimal = Field(gt=0)
    residual_rate: Decimal = Field(ge=0, lt=1, default=Decimal("0"))
    useful_life_months: int = Field(gt=0)
    department_aux_id: int | None = None
    expense_account_id: int | None = None
    accumulated_account_id: int | None = None


class DepreciationRunPayload(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class InvoicePayload(BaseModel):
    book_id: int
    invoice_code: str = Field(default="", max_length=64)
    invoice_no: str = Field(min_length=1, max_length=128)
    invoice_type: str = Field(min_length=1, max_length=32)
    direction: Literal["in", "out"]
    invoice_date: date
    amount_excluding_tax: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(ge=0)
    counterparty_aux_id: int | None = None
    currency_code: str = "CNY"
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class PayrollPayload(BaseModel):
    book_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    employee_aux_id: int
    department_aux_id: int | None = None
    gross_amount: Decimal = Field(ge=0)
    social_security_amount: Decimal = Field(ge=0, default=Decimal("0"))
    housing_fund_amount: Decimal = Field(ge=0, default=Decimal("0"))
    tax_amount: Decimal = Field(ge=0, default=Decimal("0"))
    other_deduction: Decimal = Field(ge=0, default=Decimal("0"))
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class TaxRecordPayload(BaseModel):
    book_id: int
    tax_type: str = Field(min_length=1, max_length=64)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    tax_amount: Decimal = Field(ge=0)
    taxable_amount: Decimal = Field(ge=0, default=Decimal("0"))
    due_date: date | None = None
    source_system: str = "manual"
    source_database: str = ""
    source_pk: str | None = None


class TaxPaidPayload(BaseModel):
    paid_date: date
    reason: str = Field(min_length=1, max_length=1000)


class AutoEntryRulePayload(BaseModel):
    book_id: int
    rule_name: str = Field(min_length=1, max_length=128)
    business_type: str = Field(min_length=1, max_length=64)
    source_system: str = Field(min_length=1, max_length=32)
    entry_template: dict
    effective_from: str = Field(pattern=r"^\d{4}-\d{2}$")
    effective_to: str | None = None
    priority: int = 100
    conditions: dict = Field(default_factory=dict)
    status: str = "active"


class AutoEntryRunPayload(BaseModel):
    rule_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    source_data: list[dict] = Field(default_factory=list)
    mode: Literal["preview", "draft"] = "preview"


class PeriodClosePayload(BaseModel):
    book_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    reason: str = Field(min_length=1, max_length=1000)


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


# --------------------------------------------------------------------------- #
# Books / periods                                                              #
# --------------------------------------------------------------------------- #

@router.get("/books", response_model=ApiResponse)
async def list_books(
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_books()
    return ApiResponse.ok(data=data)


@router.get("/books/{book_id}", response_model=ApiResponse)
async def get_book(
    book_id: int = Path(..., ge=1),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).get_book(book_id)
    return ApiResponse.ok(data=data)


@router.get("/periods", response_model=ApiResponse)
async def list_periods(
    book_id: int = Query(..., ge=1),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_periods(book_id)
    return ApiResponse.ok(data=data)


@router.post("/periods/close", response_model=ApiResponse)
async def close_period(
    body: PeriodClosePayload,
    current_user: SysUser = Depends(require_permission("finance:period:close")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).close_period(body.book_id, body.period, _actor_name(current_user), body.reason)
    return ApiResponse.ok(data=data, message="期间已结账")


@router.post("/periods/reopen", response_model=ApiResponse)
async def reopen_period(
    body: PeriodClosePayload,
    current_user: SysUser = Depends(require_permission("finance:period:close")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).reopen_period(body.book_id, body.period, _actor_name(current_user), body.reason)
    return ApiResponse.ok(data=data, message="期间已反结账")


@router.post("/periods/profit-loss-carryover", response_model=ApiResponse)
async def profit_loss_carryover(
    body: PeriodClosePayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).profit_loss_carryover(
        body.book_id, body.period, _actor_name(current_user), body.reason
    )
    return ApiResponse.ok(data=data, message="期末损益结转完成")


# --------------------------------------------------------------------------- #
# Accounts / auxiliary                                                         #
# --------------------------------------------------------------------------- #

@router.get("/accounts", response_model=ApiResponse)
async def list_accounts(
    book_id: int = Query(..., ge=1),
    parent_id: int | None = Query(None),
    only_active: bool = Query(True),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_accounts(book_id, parent_id=parent_id, only_active=only_active)
    return ApiResponse.ok(data=data)


@router.get("/aux-categories", response_model=ApiResponse)
async def list_aux_categories(
    book_id: int = Query(..., ge=1),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_aux_categories(book_id)
    return ApiResponse.ok(data=data)


@router.post("/aux-categories", response_model=ApiResponse)
async def upsert_aux_category(
    body: AuxCategoryPayload,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).upsert_aux_category(body.book_id, body.category_code, body.category_name, body.status)
    return ApiResponse.ok(data=data)


@router.get("/aux-items", response_model=ApiResponse)
async def list_aux_items(
    book_id: int = Query(..., ge=1),
    category_id: int | None = Query(None),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_aux_items(book_id, category_id=category_id)
    return ApiResponse.ok(data=data)


@router.post("/aux-items", response_model=ApiResponse)
async def upsert_aux_item(
    body: AuxItemPayload,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).upsert_aux_item(
        body.book_id,
        body.category_id,
        body.item_code,
        body.item_name,
        target_type=body.target_type,
        target_code=body.target_code,
    )
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Voucher lifecycle                                                           #
# --------------------------------------------------------------------------- #

@router.get("/vouchers", response_model=ApiResponse)
async def list_vouchers(
    book_id: int = Query(..., ge=1),
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    status: str | None = Query(None),
    origin_kind: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_vouchers(
        book_id, period=period, status=status, origin_kind=origin_kind, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)


@router.get("/vouchers/{voucher_id}", response_model=ApiResponse)
async def get_voucher(
    voucher_id: int = Path(..., ge=1),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).get_voucher(voucher_id)
    return ApiResponse.ok(data=data)


@router.post("/vouchers/{voucher_id}/review", response_model=ApiResponse)
async def review_voucher(
    voucher_id: int = Path(..., ge=1),
    body: ReasonPayload = ...,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).review_voucher(voucher_id, _actor_name(current_user), body.reason)
    return ApiResponse.ok(data=data, message="凭证已审核")


@router.post("/vouchers/{voucher_id}/unpost", response_model=ApiResponse)
async def unpost_voucher(
    voucher_id: int = Path(..., ge=1),
    body: ReasonPayload = ...,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).unpost_voucher(voucher_id, _actor_name(current_user), body.reason)
    return ApiResponse.ok(data=data, message="凭证已反过账")


@router.delete("/vouchers/{voucher_id}", response_model=ApiResponse)
async def delete_voucher(
    voucher_id: int = Path(..., ge=1),
    body: ReasonPayload = ...,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).delete_voucher(voucher_id, _actor_name(current_user), body.reason)
    return ApiResponse.ok(data=data, message="草稿凭证已删除")


# --------------------------------------------------------------------------- #
# Ledger queries                                                              #
# --------------------------------------------------------------------------- #

@router.get("/ledger/balances", response_model=ApiResponse)
async def list_ledger_balances(
    book_id: int = Query(..., ge=1),
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    account_id: int | None = Query(None),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_ledger_balances(book_id, period, account_id=account_id)
    return ApiResponse.ok(data=data)


@router.get("/ledger/general-ledger", response_model=ApiResponse)
async def general_ledger(
    book_id: int = Query(..., ge=1),
    account_id: int = Query(..., ge=1),
    start_period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    end_period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).general_ledger(book_id, account_id, start_period, end_period)
    return ApiResponse.ok(data=data)


@router.get("/ledger/subsidiary-ledger", response_model=ApiResponse)
async def subsidiary_ledger(
    book_id: int = Query(..., ge=1),
    account_id: int = Query(..., ge=1),
    start_period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    end_period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).subsidiary_ledger(book_id, account_id, start_period, end_period)
    return ApiResponse.ok(data=data)


@router.get("/ledger/trial-balance", response_model=ApiResponse)
async def trial_balance(
    book_id: int = Query(..., ge=1),
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).trial_balance(book_id, period)
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Receivables / payables / settlements                                        #
# --------------------------------------------------------------------------- #

@router.post("/receivables", response_model=ApiResponse)
async def create_receivable(
    body: ReceivablePayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_receivable(
        body.book_id,
        body.document_no,
        body.counterparty_aux_id,
        body.business_date,
        body.original_amount,
        currency_code=body.currency_code,
        due_date=body.due_date,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="应收单已创建")


@router.get("/receivables", response_model=ApiResponse)
async def list_receivables(
    book_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    counterparty_aux_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_receivables(
        book_id, status=status, counterparty_aux_id=counterparty_aux_id, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)


@router.post("/payables", response_model=ApiResponse)
async def create_payable(
    body: PayablePayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_payable(
        body.book_id,
        body.document_no,
        body.counterparty_aux_id,
        body.business_date,
        body.original_amount,
        currency_code=body.currency_code,
        due_date=body.due_date,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="应付单已创建")


@router.get("/payables", response_model=ApiResponse)
async def list_payables(
    book_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    counterparty_aux_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_payables(
        book_id, status=status, counterparty_aux_id=counterparty_aux_id, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)


@router.post("/settlements", response_model=ApiResponse)
async def create_settlement(
    body: SettlementPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_settlement(
        body.book_id,
        body.settlement_type,
        body.receivable_id,
        body.payable_id,
        body.settlement_date,
        body.amount,
        _actor_name(current_user),
        body.reason,
    )
    return ApiResponse.ok(data=data, message="核销已创建")


@router.get("/settlements", response_model=ApiResponse)
async def list_settlements(
    book_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_settlements(book_id, page=page, page_size=page_size)
    return ApiResponse.ok(data=data)


@router.get("/aging", response_model=ApiResponse)
async def aging_analysis(
    book_id: int = Query(..., ge=1),
    as_of: date | None = Query(None),
    kind: Literal["receivable", "payable"] = Query("receivable"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).aging_analysis(book_id, as_of=as_of, kind=kind)
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Cashier                                                                     #
# --------------------------------------------------------------------------- #

@router.get("/cash-accounts", response_model=ApiResponse)
async def list_cash_accounts(
    book_id: int = Query(..., ge=1),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_cash_accounts(book_id)
    return ApiResponse.ok(data=data)


@router.post("/cash-accounts", response_model=ApiResponse)
async def upsert_cash_account(
    body: CashAccountPayload,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).upsert_cash_account(
        body.book_id,
        body.account_code,
        body.account_name,
        body.account_type,
        body.ledger_account_id,
        bank_name=body.bank_name,
        bank_account_masked=body.bank_account_masked,
        currency_code=body.currency_code,
    )
    return ApiResponse.ok(data=data)


@router.post("/bank-transactions", response_model=ApiResponse)
async def create_bank_transaction(
    body: BankTransactionPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_bank_transaction(
        body.book_id,
        body.cash_account_id,
        body.transaction_date,
        body.amount,
        body.direction,
        counterparty_name=body.counterparty_name,
        reference_no=body.reference_no,
        summary=body.summary,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="银行流水已采集")


@router.get("/bank-transactions", response_model=ApiResponse)
async def list_bank_transactions(
    book_id: int = Query(..., ge=1),
    cash_account_id: int | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_bank_transactions(
        book_id, cash_account_id=cash_account_id, status=status, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)


@router.post("/reconciliations", response_model=ApiResponse)
async def create_reconciliation(
    body: ReconciliationPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_reconciliation(
        body.book_id,
        body.cash_account_id,
        body.period,
        body.statement_balance,
        body.ledger_balance,
        matched_transaction_ids=body.matched_transaction_ids,
        actor_name=_actor_name(current_user),
    )
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Fixed assets                                                                #
# --------------------------------------------------------------------------- #

@router.get("/fixed-assets", response_model=ApiResponse)
async def list_fixed_assets(
    book_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_fixed_assets(book_id, status=status)
    return ApiResponse.ok(data=data)


@router.post("/fixed-assets", response_model=ApiResponse)
async def create_fixed_asset(
    body: FixedAssetPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_fixed_asset(
        body.book_id,
        body.asset_code,
        body.asset_name,
        body.category,
        body.acquisition_date,
        body.in_service_date,
        body.original_cost,
        body.useful_life_months,
        residual_rate=body.residual_rate,
        department_aux_id=body.department_aux_id,
        expense_account_id=body.expense_account_id,
        accumulated_account_id=body.accumulated_account_id,
        actor_name=_actor_name(current_user),
    )
    return ApiResponse.ok(data=data, message="固定资产已建档")


@router.post("/fixed-assets/{fixed_asset_id}/depreciate", response_model=ApiResponse)
async def run_depreciation(
    fixed_asset_id: int = Path(..., ge=1),
    body: DepreciationRunPayload = ...,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).calculate_depreciation(
        fixed_asset_id, body.period, _actor_name(current_user)
    )
    return ApiResponse.ok(data=data, message="折旧已计提")


@router.get("/depreciations", response_model=ApiResponse)
async def list_depreciations(
    book_id: int = Query(..., ge=1),
    fixed_asset_id: int | None = Query(None),
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_depreciations(
        book_id, fixed_asset_id=fixed_asset_id, period=period
    )
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Invoices                                                                    #
# --------------------------------------------------------------------------- #

@router.get("/invoices", response_model=ApiResponse)
async def list_invoices(
    book_id: int = Query(..., ge=1),
    direction: Literal["in", "out"] | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_invoices(
        book_id, direction=direction, status=status, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)


@router.post("/invoices", response_model=ApiResponse)
async def create_invoice(
    body: InvoicePayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_invoice(
        body.book_id,
        body.invoice_code,
        body.invoice_no,
        body.invoice_type,
        body.direction,
        body.invoice_date,
        body.amount_excluding_tax,
        body.tax_amount,
        counterparty_aux_id=body.counterparty_aux_id,
        currency_code=body.currency_code,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="发票已登记")


# --------------------------------------------------------------------------- #
# Payroll                                                                     #
# --------------------------------------------------------------------------- #

@router.get("/payrolls", response_model=ApiResponse)
async def list_payrolls(
    book_id: int = Query(..., ge=1),
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    employee_aux_id: int | None = Query(None),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_payrolls(book_id, period=period, employee_aux_id=employee_aux_id)
    return ApiResponse.ok(data=data)


@router.post("/payrolls", response_model=ApiResponse)
async def create_payroll(
    body: PayrollPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_payroll(
        body.book_id,
        body.period,
        body.employee_aux_id,
        body.gross_amount,
        social_security_amount=body.social_security_amount,
        housing_fund_amount=body.housing_fund_amount,
        tax_amount=body.tax_amount,
        other_deduction=body.other_deduction,
        department_aux_id=body.department_aux_id,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="工资已入账")


# --------------------------------------------------------------------------- #
# Tax                                                                         #
# --------------------------------------------------------------------------- #

@router.get("/tax-records", response_model=ApiResponse)
async def list_tax_records(
    book_id: int = Query(..., ge=1),
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_tax_records(book_id, period=period)
    return ApiResponse.ok(data=data)


@router.post("/tax-records", response_model=ApiResponse)
async def create_tax_record(
    body: TaxRecordPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).create_tax_record(
        body.book_id,
        body.tax_type,
        body.period,
        body.tax_amount,
        taxable_amount=body.taxable_amount,
        due_date=body.due_date,
        actor_name=_actor_name(current_user),
        source_system=body.source_system,
        source_database=body.source_database,
        source_pk=body.source_pk,
    )
    return ApiResponse.ok(data=data, message="税务记录已创建")


@router.post("/tax-records/{tax_record_id}/mark-paid", response_model=ApiResponse)
async def mark_tax_paid(
    tax_record_id: int = Path(..., ge=1),
    body: TaxPaidPayload = ...,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).mark_tax_paid(
        tax_record_id, body.paid_date, _actor_name(current_user), body.reason
    )
    return ApiResponse.ok(data=data, message="税务已标记为已缴")


# --------------------------------------------------------------------------- #
# Auto entry rules / runs                                                     #
# --------------------------------------------------------------------------- #

@router.get("/auto-entry-rules", response_model=ApiResponse)
async def list_auto_entry_rules(
    book_id: int = Query(..., ge=1),
    status: str | None = Query(None),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_auto_entry_rules(book_id, status=status)
    return ApiResponse.ok(data=data)


@router.post("/auto-entry-rules", response_model=ApiResponse)
async def upsert_auto_entry_rule(
    body: AutoEntryRulePayload,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).upsert_auto_entry_rule(
        body.book_id,
        body.rule_name,
        body.business_type,
        body.source_system,
        body.entry_template,
        body.effective_from,
        effective_to=body.effective_to,
        priority=body.priority,
        conditions=body.conditions,
        status=body.status,
    )
    return ApiResponse.ok(data=data, message="自动凭证规则已保存")


@router.post("/auto-entry-rules/run", response_model=ApiResponse)
async def run_auto_entry(
    body: AutoEntryRunPayload,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).run_auto_entry(
        body.rule_id, body.source_data, body.period, _actor_name(current_user), mode=body.mode
    )
    return ApiResponse.ok(data=data)


@router.get("/auto-entry-runs", response_model=ApiResponse)
async def list_auto_entry_runs(
    book_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_auto_entry_runs(book_id, page=page, page_size=page_size)
    return ApiResponse.ok(data=data)


# --------------------------------------------------------------------------- #
# Operation logs                                                              #
# --------------------------------------------------------------------------- #

@router.get("/operation-logs", response_model=ApiResponse)
async def list_operation_logs(
    book_id: int = Query(..., ge=1),
    target_type: str | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterOpsService(db).list_operation_logs(
        book_id, target_type=target_type, action=action, page=page, page_size=page_size
    )
    return ApiResponse.ok(data=data)
