"""Writable formal finance-center API."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.finance_center_service import FinanceCenterService

router = APIRouter(prefix="/finance-center", tags=["正式财务中心"])


class KingdeeImportRequest(BaseModel):
    account_set_code: str = Field(min_length=1, max_length=128)


class PeriodOpenRequest(BaseModel):
    book_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class VoucherEntryPayload(BaseModel):
    account_id: int
    summary: str = Field(min_length=1, max_length=512)
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    currency_code: str = "CNY"
    exchange_rate: Decimal = Decimal("1")
    aux_items: dict = Field(default_factory=dict)


class VoucherCreateRequest(BaseModel):
    book_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    voucher_no: str = Field(min_length=1, max_length=64)
    voucher_date: date
    reason: str = Field(min_length=1, max_length=1000)
    entries: list[VoucherEntryPayload] = Field(min_length=1)


class VoucherRevisionRequest(ReasonRequest):
    entries: list[VoucherEntryPayload] = Field(min_length=1)


class VoucherReverseRequest(ReasonRequest):
    voucher_no: str = Field(min_length=1, max_length=64)


class StatementLineRequest(BaseModel):
    template_code: str = Field(min_length=1, max_length=64)
    template_version: int = Field(ge=1)
    statement_type: str = Field(pattern=r"^(balance_sheet|income_statement|cashflow)$")
    line_code: str = Field(min_length=1, max_length=64)
    line_name: str = Field(min_length=1, max_length=128)
    display_order: int = 0


class StatementMappingRequest(BaseModel):
    book_id: int
    account_id: int
    statement_line_id: int
    amount_sign: Literal[-1, 1] = 1


class StatementGenerateRequest(BaseModel):
    book_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    statement_type: str = Field(pattern=r"^(balance_sheet|income_statement|cashflow)$")


def _actor_name(user: SysUser) -> str:
    return str(getattr(user, "username", None) or getattr(user, "name", None) or getattr(user, "id", "system"))


def _entry_dicts(entries: list[VoucherEntryPayload]) -> list[dict]:
    return [entry.model_dump() for entry in entries]


@router.post("/kingdee/import", response_model=ApiResponse)
async def import_kingdee_history(
    body: KingdeeImportRequest,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).import_kingdee_history_to_formal_ledger(body.account_set_code)
    return ApiResponse.ok(data=data, message="金蝶历史账套已写入正式财务账簿")


@router.post("/periods/open", response_model=ApiResponse)
async def open_period(
    body: PeriodOpenRequest,
    current_user: SysUser = Depends(require_permission("finance:period:close")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).open_period(body.book_id, body.period)
    return ApiResponse.ok(data=data)


@router.post("/vouchers", response_model=ApiResponse)
async def create_voucher(
    body: VoucherCreateRequest,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).create_voucher(
        body.book_id,
        period=body.period,
        voucher_no=body.voucher_no,
        voucher_date=body.voucher_date,
        entries=_entry_dicts(body.entries),
        actor_name=_actor_name(current_user),
        reason=body.reason,
    )
    return ApiResponse.ok(data=data, message="凭证草稿已创建")


@router.post("/vouchers/{voucher_id}/post", response_model=ApiResponse)
async def post_voucher(
    voucher_id: int,
    body: ReasonRequest,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).post_voucher(
        voucher_id, actor_name=_actor_name(current_user), reason=body.reason
    )
    return ApiResponse.ok(data=data, message="凭证已过账")


@router.post("/vouchers/{voucher_id}/reverse", response_model=ApiResponse)
async def reverse_voucher(
    voucher_id: int,
    body: VoucherReverseRequest,
    current_user: SysUser = Depends(require_permission("finance:voucher:post")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).reverse_voucher(
        voucher_id,
        voucher_no=body.voucher_no,
        actor_name=_actor_name(current_user),
        reason=body.reason,
    )
    return ApiResponse.ok(data=data, message="冲销凭证已生成")


@router.post("/vouchers/{voucher_id}/revise-entries", response_model=ApiResponse)
async def revise_voucher_entries(
    voucher_id: int,
    body: VoucherRevisionRequest,
    current_user: SysUser = Depends(require_permission("finance:voucher:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).revise_voucher_entries(
        voucher_id,
        entries=_entry_dicts(body.entries),
        actor_name=_actor_name(current_user),
        reason=body.reason,
    )
    return ApiResponse.ok(data=data, message="凭证分录已修订")


@router.post("/statement-lines", response_model=ApiResponse)
async def upsert_statement_line(
    body: StatementLineRequest,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).upsert_statement_line(**body.model_dump())
    return ApiResponse.ok(data=data)


@router.post("/statement-mappings", response_model=ApiResponse)
async def map_account_to_statement(
    body: StatementMappingRequest,
    current_user: SysUser = Depends(require_permission("finance:settings:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).map_account_to_statement(
        book_id=body.book_id,
        account_id=body.account_id,
        statement_line_id=body.statement_line_id,
        amount_sign=body.amount_sign,
        actor_name=_actor_name(current_user),
    )
    return ApiResponse.ok(data=data)


@router.post("/statements/generate", response_model=ApiResponse)
async def generate_statement_monthly(
    body: StatementGenerateRequest,
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).generate_statement_monthly(
        body.book_id,
        period=body.period,
        statement_type=body.statement_type,
    )
    return ApiResponse.ok(data=data)


@router.get("/statements", response_model=ApiResponse)
async def get_statement_monthly(
    book_id: int,
    period: str = Query(pattern=r"^\d{4}-\d{2}$"),
    statement_type: str = Query(pattern=r"^(balance_sheet|income_statement|cashflow)$"),
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await FinanceCenterService(db).get_statement_monthly(book_id, period, statement_type)
    return ApiResponse.ok(data=data)
