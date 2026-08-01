"""牧马人财务中心的独立 API，不依赖华邦旧财务模块。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission, require_roles
from app.core.database import get_db
from app.models.mumaren_finance_center import FinanceCenterMumarenVoucher
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.mumaren_finance_center.workflow import (
    InvalidVoucherTransition,
    UnbalancedVoucherError,
    create_voucher as create_mumaren_voucher,
    list_accounts,
    list_books,
    list_history_vouchers,
    post_voucher_by_id,
    review_voucher_by_id,
)
from app.services.mumaren_finance_center.reports import (
    get_cash_flow_statement,
    get_profit_statement,
    get_trial_balance,
)


router = APIRouter(prefix="/finance-center/mumaren", tags=["牧马人财务中心"])

def require_mumaren_finance_permission(permission_code: str):
    role_gate = require_roles("finance_manager", "finance")
    permission_gate = require_permission(permission_code)

    async def gate(
        role_user: SysUser = Depends(role_gate),
        permission_user: SysUser = Depends(permission_gate),
    ) -> SysUser:
        return permission_user

    return gate


require_mumaren_finance_access = require_mumaren_finance_permission("mumaren_finance_center:access")
require_mumaren_voucher_view = require_mumaren_finance_permission("mumaren_finance_center:voucher:view")
require_mumaren_voucher_write = require_mumaren_finance_permission("mumaren_finance_center:voucher:write")
require_mumaren_voucher_review = require_mumaren_finance_permission("mumaren_finance_center:voucher:review")
require_mumaren_voucher_post = require_mumaren_finance_permission("mumaren_finance_center:voucher:post")
require_mumaren_history_view = require_mumaren_finance_permission("mumaren_finance_center:history:view")


class VoucherLineInput(BaseModel):
    account_id: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=500)
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0)


class VoucherCreateInput(BaseModel):
    book_id: int = Field(ge=1)
    voucher_no: str = Field(min_length=1, max_length=64)
    voucher_date: date
    summary: str | None = Field(default=None, max_length=500)
    voucher_type: str = Field(default="记", min_length=1, max_length=16)
    lines: list[VoucherLineInput] = Field(min_length=1)


def _actor_id(user: SysUser) -> int:
    return int(user.id)


def _voucher_data(voucher: FinanceCenterMumarenVoucher) -> dict:
    return {
        "id": voucher.id,
        "book_id": voucher.book_id,
        "voucher_no": voucher.voucher_no,
        "voucher_date": voucher.voucher_date,
        "summary": voucher.summary,
        "status": voucher.status,
        "total_debit": voucher.total_debit,
        "total_credit": voucher.total_credit,
        "reviewed_by": voucher.reviewed_by,
        "posted_by": voucher.posted_by,
    }


@router.get("/catalog", response_model=ApiResponse)
async def catalog(current_user: SysUser = Depends(require_mumaren_finance_access)):
    return ApiResponse.ok(data={
        "module": "mumaren_finance_center",
        "capabilities": ["books", "accounts", "vouchers", "manual_review_posting", "history_readonly"],
        "operator_id": _actor_id(current_user),
    })


@router.get("/books", response_model=ApiResponse)
async def get_books(
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    books = await list_books(db)
    return ApiResponse.ok(data=[{
        "id": book.id, "book_code": book.book_code, "book_name": book.book_name,
        "company_name": book.company_name, "status": book.status,
    } for book in books])


@router.get("/books/{book_id}/accounts", response_model=ApiResponse)
async def get_accounts(
    book_id: int,
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    accounts = await list_accounts(db, book_id=book_id)
    return ApiResponse.ok(data=[{
        "id": account.id, "account_code": account.account_code, "account_name": account.account_name,
        "account_type": account.account_type, "direction": account.direction, "level": account.level,
    } for account in accounts])


@router.get("/vouchers", response_model=ApiResponse)
async def get_vouchers(
    book_id: int | None = Query(default=None, ge=1),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    statement = select(FinanceCenterMumarenVoucher).order_by(FinanceCenterMumarenVoucher.id.desc())
    if book_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucher.book_id == book_id)
    result = await db.execute(statement.limit(200))
    return ApiResponse.ok(data=[_voucher_data(voucher) for voucher in result.scalars()])


@router.post("/vouchers", response_model=ApiResponse)
async def create_voucher(
    body: VoucherCreateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        voucher = await create_mumaren_voucher(
            db,
            book_id=body.book_id,
            voucher_no=body.voucher_no,
            voucher_date=body.voucher_date,
            summary=body.summary,
            voucher_type=body.voucher_type,
            lines=[line.model_dump() for line in body.lines],
            operator_id=_actor_id(current_user),
        )
    except (UnbalancedVoucherError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ApiResponse.ok(data=_voucher_data(voucher), message="凭证草稿已创建")


@router.post("/vouchers/{voucher_id}/review", response_model=ApiResponse)
async def review_voucher(
    voucher_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    try:
        voucher = await review_voucher_by_id(db, voucher_id=voucher_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidVoucherTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data=_voucher_data(voucher), message="凭证已审核")


@router.post("/vouchers/{voucher_id}/post", response_model=ApiResponse)
async def post_voucher(
    voucher_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    try:
        voucher = await post_voucher_by_id(db, voucher_id=voucher_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidVoucherTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data=_voucher_data(voucher), message="凭证已人工过账")


@router.get("/history/vouchers", response_model=ApiResponse)
async def get_history_vouchers(
    source_system: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_history_view),
    db: AsyncSession = Depends(get_db),
):
    vouchers = await list_history_vouchers(db, source_system=source_system, limit=limit)
    return ApiResponse.ok(data=[{
        "id": voucher.id, "source_system": voucher.source_system, "source_key": voucher.source_key,
        "record_type": voucher.record_type, "is_readonly": voucher.is_readonly,
        "voucher_no": voucher.voucher_no, "voucher_date": voucher.voucher_date, "summary": voucher.summary,
    } for voucher in vouchers])


@router.get("/reports/trial-balance", response_model=ApiResponse)
async def get_trial_balance_report(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    """当前账已过账凭证的科目余额与试算平衡；历史区不参与计算。"""
    try:
        return ApiResponse.ok(data=await get_trial_balance(db, book_id=book_id, period=period))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports/profit-statement", response_model=ApiResponse)
async def get_profit_statement_report(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    """当前账已过账凭证的利润表；空账返回零值而非模拟经营数据。"""
    try:
        return ApiResponse.ok(data=await get_profit_statement(db, book_id=book_id, period=period))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports/cash-flow-statement", response_model=ApiResponse)
async def get_cash_flow_statement_report(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    """现金流量表：联动已过账 cash_flows 表的经营活动/投资/筹资现金流。"""
    try:
        return ApiResponse.ok(data=await get_cash_flow_statement(db, book_id=book_id, period=period))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
