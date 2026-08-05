"""牧马人财务中心的独立 API，不依赖华邦旧财务模块。"""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission, require_roles
from app.core.database import get_db
from app.models.mumaren_finance_center import FinanceCenterMumarenAccount, FinanceCenterMumarenAuditLog, FinanceCenterMumarenBalanceSnapshot, FinanceCenterMumarenBook, FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucherLine
from app.models.mumaren_finance_center_auxiliary import FinanceCenterMumarenVoucherLineAuxiliary
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.mumaren_finance_center.workflow import (
    InvalidVoucherTransition,
    UnbalancedVoucherError,
    create_book as create_mumaren_book,
    create_account as create_mumaren_account,
    update_account as update_mumaren_account,
    replenish_starter_accounts,
    replace_account_auxiliary_dimensions,
    update_book as update_mumaren_book,
    create_voucher as create_mumaren_voucher,
    list_account_auxiliary_dimensions,
    list_accounts,
    list_books,
    list_history_vouchers,
    next_voucher_number,
    post_voucher_by_id,
    review_voucher_by_id,
)
from app.services.mumaren_finance_center.reports import (
    get_cash_flow_statement,
    get_profit_statement,
    get_trial_balance,
)
from app.services.mumaren_finance_center.voucher_summary import (
    VoucherSummaryFilters,
    build_detail_count_statement,
    build_detail_statement,
    build_period_options_statement,
    build_summary_statement,
    build_voucher_type_options_statement,
    serialize_summary_rows,
)
from app.services.mumaren_finance_center.voucher_query import (
    VoucherQueryFilters,
    build_voucher_count_statement,
    build_voucher_line_count_statement,
    build_voucher_line_statement,
    build_voucher_statement,
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


class VoucherLineAuxiliaryInput(BaseModel):
    aux_type: str = Field(pattern=r"^(customer|supplier|employee|project|department)$")
    auxiliary_id: int = Field(ge=1)


class VoucherLineInput(BaseModel):
    account_id: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=500)
    summary_explicitly_cleared: bool = False
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    auxiliaries: list[VoucherLineAuxiliaryInput] = Field(default_factory=list)


class VoucherCreateInput(BaseModel):
    book_id: int = Field(ge=1)
    voucher_no: str | None = Field(default=None, max_length=64)
    voucher_date: date
    summary: str | None = Field(default=None, max_length=500)
    voucher_type: str = Field(default="记", min_length=1, max_length=16)
    lines: list[VoucherLineInput] = Field(min_length=1)


class BookCreateInput(BaseModel):
    book_code: str = Field(min_length=1, max_length=64)
    book_name: str = Field(min_length=1, max_length=128)
    company_name: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")


class BookUpdateInput(BaseModel):
    book_name: str | None = Field(default=None, min_length=1, max_length=128)
    # The client always sends this field so null explicitly clears an optional company name.
    company_name: str | None


class AccountCreateInput(BaseModel):
    account_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    account_type: str = Field(pattern=r"^(asset|liability|equity|income|expense)$")
    direction: str = Field(pattern=r"^(debit|credit)$")
    level: int = Field(default=1, ge=1, le=10)


class AccountUpdateInput(BaseModel):
    book_id: int = Field(ge=1)
    account_name: str | None = Field(default=None, min_length=1, max_length=128)
    account_type: str | None = Field(default=None, pattern=r"^(asset|liability|equity|income|expense)$")
    direction: str | None = Field(default=None, pattern=r"^(debit|credit)$")
    level: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None


class AccountAuxiliaryDimensionsInput(BaseModel):
    book_id: int = Field(ge=1)
    auxiliary_types: list[str] = Field(default_factory=list, max_length=5)


def _actor_id(user: SysUser) -> int:
    return int(user.id)


def _voucher_data(voucher: FinanceCenterMumarenVoucher) -> dict:
    return {
        "id": voucher.id,
        "book_id": voucher.book_id,
        "voucher_no": voucher.voucher_no,
        "voucher_type": voucher.voucher_type,
        "voucher_date": voucher.voucher_date,
        "summary": voucher.summary,
        "status": voucher.status,
        "total_debit": voucher.total_debit,
        "total_credit": voucher.total_credit,
        "created_by": voucher.created_by,
        "created_at": voucher.created_at,
        "reviewed_by": voucher.reviewed_by,
        "reviewed_at": voucher.reviewed_at,
        "posted_by": voucher.posted_by,
        "posted_at": voucher.posted_at,
        "is_readonly": voucher.is_readonly,
        "is_normalized": voucher.is_normalized,
        "source_system": voucher.source_system,
        "source_database": voucher.source_database,
        "source_key": voucher.source_key,
        "import_batch_key": voucher.import_batch_key,
    }


def validate_voucher_query_dates(date_from: date | None, date_to: date | None, period: str | None) -> None:
    if period and (date_from or date_to):
        raise ValueError("日期范围与期间不能同时查询")
    if date_from and date_to and date_from > date_to:
        raise ValueError("开始日期不能晚于结束日期")


def _serialize_auxiliaries(rows: list[FinanceCenterMumarenVoucherLineAuxiliary]) -> list[dict]:
    return [{
        "aux_type": item.aux_type,
        "auxiliary_id": item.auxiliary_id,
        "auxiliary_code": item.auxiliary_code_snapshot,
        "auxiliary_name": item.auxiliary_name_snapshot,
    } for item in rows]


def _auxiliary_display(rows: list[FinanceCenterMumarenVoucherLineAuxiliary]) -> str:
    return "；".join(f"{item.auxiliary_code_snapshot} {item.auxiliary_name_snapshot}".strip() for item in rows) or "—"


def _voucher_line_query_data(
    line: FinanceCenterMumarenVoucherLine,
    voucher: FinanceCenterMumarenVoucher,
    account: FinanceCenterMumarenAccount,
    *,
    inherited_summary: str,
    auxiliaries: list[FinanceCenterMumarenVoucherLineAuxiliary],
) -> dict:
    return {
        "id": line.id, "voucher_id": voucher.id, "voucher_date": voucher.voucher_date,
        "voucher_no": voucher.voucher_no, "voucher_type": voucher.voucher_type,
        "line_no": line.line_no,
        "line_summary": resolve_ledger_line_summary(
            line, inherited_summary=inherited_summary, voucher_summary=voucher.summary,
        ),
        "account_id": account.id, "account_code": account.account_code, "account_name": account.account_name,
        "debit_amount": line.debit_amount, "credit_amount": line.credit_amount,
        "status": voucher.status, "auxiliaries": _auxiliary_display(auxiliaries),
    }


def _voucher_detail_data(
    voucher: FinanceCenterMumarenVoucher,
    line_accounts: list[tuple[FinanceCenterMumarenVoucherLine, FinanceCenterMumarenAccount]],
    auxiliaries_by_line: dict[int, list[FinanceCenterMumarenVoucherLineAuxiliary]],
) -> dict:
    inherited_summary = ""
    lines = []
    for line, account in line_accounts:
        line_data = _voucher_line_query_data(
            line, voucher, account, inherited_summary=inherited_summary,
            auxiliaries=auxiliaries_by_line.get(line.id, []),
        )
        line_data["auxiliary_values"] = _serialize_auxiliaries(auxiliaries_by_line.get(line.id, []))
        lines.append(line_data)
        if line.summary:
            inherited_summary = line.summary
    return {
        **_voucher_data(voucher),
        "lines": lines,
        "is_balanced": voucher.total_debit == voucher.total_credit,
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
        "is_readonly": book.is_readonly,
        "source_system": book.source_system,
        "source_database": book.source_database,
    } for book in books])


@router.post("/books", response_model=ApiResponse)
async def create_book_endpoint(
    body: BookCreateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        book = await create_mumaren_book(
            db, book_code=body.book_code, book_name=body.book_name,
            company_name=body.company_name, status=body.status, operator_id=_actor_id(current_user),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ApiResponse.ok(data={
        "id": book.id, "book_code": book.book_code, "book_name": book.book_name,
        "company_name": book.company_name, "status": book.status,
    }, message="账簿已创建并完成基础数据初始化")


@router.put("/books/{book_id}", response_model=ApiResponse)
async def update_book_endpoint(
    book_id: int, body: BookUpdateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db),
):
    try:
        book = await update_mumaren_book(
            db, book_id=book_id, book_name=body.book_name, company_name=body.company_name,
            operator_id=_actor_id(current_user),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data={
        "id": book.id, "book_code": book.book_code, "book_name": book.book_name,
        "company_name": book.company_name, "status": book.status, "is_readonly": book.is_readonly,
    }, message="账簿已更新")


@router.post("/books/{book_id}/starter-accounts", response_model=ApiResponse)
async def replenish_starter_accounts_endpoint(
    book_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db),
):
    try:
        added = await replenish_starter_accounts(db, book_id=book_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data={"added": added}, message=f"已补齐 {added} 个基础科目")


@router.get("/books/{book_id}/accounts", response_model=ApiResponse)
async def get_accounts(
    book_id: int,
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    accounts = await list_accounts(db, book_id=book_id)
    dimensions = await list_account_auxiliary_dimensions(db, book_id=book_id)
    return ApiResponse.ok(data=[{
        "id": account.id, "account_code": account.account_code, "account_name": account.account_name,
        "account_type": account.account_type, "direction": account.direction, "level": account.level,
        "required_auxiliary_types": [row.aux_type for row in dimensions.get(account.id, []) if row.is_required],
    } for account in accounts])


def _account_data(account: FinanceCenterMumarenAccount) -> dict:
    return {
        "id": account.id, "book_id": account.book_id, "account_code": account.account_code,
        "account_name": account.account_name, "account_type": account.account_type,
        "direction": account.direction, "level": account.level, "is_active": account.is_active,
        "required_auxiliary_types": [],
    }


async def append_report_mapping_status(
    db: AsyncSession, *, book_id: int, report: dict,
) -> dict:
    """Expose source accounts that remain intentionally unclassified for reports."""
    unclassified_count = await db.scalar(
        select(func.count())
        .select_from(FinanceCenterMumarenAccount)
        .where(
            FinanceCenterMumarenAccount.book_id == book_id,
            FinanceCenterMumarenAccount.account_type == "unclassified",
        )
    )
    return {**report, "unclassified_account_count": int(unclassified_count or 0)}


@router.get("/dingtalk-expenses", response_model=ApiResponse)
async def list_dingtalk_expenses(
    category: str | None = Query(default=None, pattern=r"^(reimbursement|payment)$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    approval_status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Read-only DingTalk reimbursement/payment evidence for the new finance centre."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    predicates: list[str] = []
    params: dict[str, object] = {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if category:
        predicates.append("category = :category")
        params["category"] = category
    if start_date:
        predicates.append("expense_date >= :start_date")
        params["start_date"] = start_date
    if end_date:
        predicates.append("expense_date <= :end_date")
        params["end_date"] = end_date
    if approval_status:
        predicates.append("approval_status = :approval_status")
        params["approval_status"] = approval_status
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""

    total = (await db.execute(text(f"SELECT count(*) FROM finance_expense_records{where}"), params)).scalar_one()
    rows = (await db.execute(text(f"""
        SELECT id, applicant_name, department_name, expense_type, amount, category,
               approval_status, payment_status, expense_date, created_at, updated_at
        FROM finance_expense_records{where}
        ORDER BY expense_date DESC NULLS LAST, id DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    return ApiResponse.ok(data={
        "items": [
            {
                "id": row["id"], "applicant_name": row["applicant_name"],
                "department_name": row["department_name"], "expense_type": row["expense_type"],
                "amount": float(row["amount"] or 0), "category": row["category"],
                "approval_status": row["approval_status"], "payment_status": row["payment_status"],
                "expense_date": str(row["expense_date"]) if row["expense_date"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            for row in rows
        ],
        "total": total, "page": page, "page_size": page_size,
        "source": "dingtalk:finance_expense_records", "readonly": True,
    })


@router.get("/cash-safety", response_model=ApiResponse)
async def get_cash_safety(
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Operating cash warning only; it never changes accounting-book reports."""
    cash = (await db.execute(text("""
        SELECT max(record_date) AS record_date, coalesce(sum(balance), 0) AS total_balance
        FROM dwd.dwd_finance_cash
        WHERE record_date = (SELECT max(record_date) FROM dwd.dwd_finance_cash)
    """))).mappings().one()
    expense = (await db.execute(text("""
        SELECT count(*) AS record_count, coalesce(sum(expense_amount), 0) AS total_expense
        FROM dwd.dwd_finance_expense
        WHERE expense_date >= current_date - interval '30 days'
          AND expense_date < current_date
    """))).mappings().one()
    daily_average = float(expense["total_expense"] or 0) / 30 if expense["record_count"] else None
    total_balance = float(cash["total_balance"] or 0)
    days = int(total_balance / daily_average) if daily_average and daily_average > 0 and cash["record_date"] else None
    risk_level = "unknown" if days is None else "critical" if days < 15 else "warning" if days < 30 else "normal"
    return ApiResponse.ok(data={
        "total_cash_balance": total_balance,
        "cash_record_date": str(cash["record_date"]) if cash["record_date"] else None,
        "daily_avg_expense_30d": daily_average,
        "expense_record_count_30d": expense["record_count"],
        "cash_safety_days": days,
        "risk_level": risk_level,
        "status": "ready" if days is not None else "pending_data",
        "note": "经营预警指标，不替代银行对账或会计报表；来源不完整时仅供参考。",
    })
@router.post("/books/{book_id}/accounts", response_model=ApiResponse)
async def create_account_endpoint(
    book_id: int, body: AccountCreateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db),
):
    try:
        account = await create_mumaren_account(
            db, book_id=book_id, operator_id=_actor_id(current_user), **body.model_dump(),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data=_account_data(account), message="科目已创建")


@router.put("/books/{book_id}/accounts/{account_id}", response_model=ApiResponse)
async def update_account_endpoint(
    book_id: int, account_id: int, body: AccountUpdateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db),
):
    if body.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿标识不一致")
    try:
        account = await update_mumaren_account(
            db, account_id=account_id, book_id=book_id, operator_id=_actor_id(current_user),
            **body.model_dump(exclude={"book_id"}),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(data=_account_data(account), message="科目已更新")


@router.put("/books/{book_id}/accounts/{account_id}/auxiliary-dimensions", response_model=ApiResponse)
async def replace_account_auxiliary_dimensions_endpoint(
    book_id: int, account_id: int, body: AccountAuxiliaryDimensionsInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db),
):
    if body.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿标识不一致")
    try:
        rows = await replace_account_auxiliary_dimensions(
            db, book_id=book_id, account_id=account_id,
            aux_types=body.auxiliary_types, operator_id=_actor_id(current_user),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.ok(
        data={"account_id": account_id, "required_auxiliary_types": [row.aux_type for row in rows]},
        message="科目辅助核算设置已更新",
    )


@router.get("/vouchers/summary", response_model=ApiResponse)
async def get_voucher_summary(
    book_id: int = Query(ge=1),
    status: Literal["draft", "reviewed", "posted"] = "posted",
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    voucher_type: str | None = Query(default=None, min_length=1, max_length=16),
    keyword: str | None = Query(default=None, max_length=500),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    filters = VoucherSummaryFilters(
        book_id=book_id, status=status, period=period, voucher_type=voucher_type, keyword=keyword,
    )
    rows = serialize_summary_rows((await db.execute(build_summary_statement(filters))).mappings().all())
    periods = [str(item[0]) for item in (await db.execute(build_period_options_statement(filters))).all()]
    voucher_types = [str(item[0]) for item in (await db.execute(build_voucher_type_options_statement(filters))).all()]
    total_debit = sum(row["total_debit"] for row in rows)
    total_credit = sum(row["total_credit"] for row in rows)
    return ApiResponse.ok(data={
        "filters": {"book_id": book_id, "status": status, "period": period, "voucher_type": voucher_type, "keyword": keyword},
        "rows": rows,
        "total_voucher_count": sum(row["voucher_count"] for row in rows),
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
        "available_periods": periods,
        "available_voucher_types": voucher_types,
    })


@router.get("/vouchers/summary/details", response_model=ApiResponse)
async def get_voucher_summary_details(
    book_id: int = Query(ge=1),
    status: Literal["draft", "reviewed", "posted"] = "posted",
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    voucher_type: str | None = Query(default=None, min_length=1, max_length=16),
    keyword: str | None = Query(default=None, max_length=500),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    filters = VoucherSummaryFilters(
        book_id=book_id, status=status, period=period, voucher_type=voucher_type, keyword=keyword,
    )
    vouchers = (await db.execute(build_detail_statement(filters, offset=offset, limit=limit))).scalars().all()
    total = int((await db.execute(build_detail_count_statement(filters))).scalar_one())
    return ApiResponse.ok(data={"items": [_voucher_data(voucher) for voucher in vouchers], "total": total, "offset": offset, "limit": limit})


async def _voucher_query_filters(
    db: AsyncSession,
    *,
    book_id: int,
    status: Literal["draft", "reviewed", "posted"] | None,
    date_from: date | None,
    date_to: date | None,
    period: str | None,
    voucher_type: str | None,
    keyword: str | None,
    account_id: int | None,
) -> VoucherQueryFilters:
    try:
        validate_voucher_query_dates(date_from, date_to, period)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    if account_id is not None:
        account = await db.get(FinanceCenterMumarenAccount, account_id)
        if account is None or account.book_id != book_id:
            raise HTTPException(status_code=404, detail="科目不属于所选账簿")
    return VoucherQueryFilters(
        book_id=book_id, status=status, date_from=date_from, date_to=date_to, period=period,
        voucher_type=voucher_type, keyword=keyword, account_id=account_id,
    )


async def _saved_auxiliaries_by_line(
    db: AsyncSession, *, book_id: int, line_ids: list[int],
) -> dict[int, list[FinanceCenterMumarenVoucherLineAuxiliary]]:
    if not line_ids:
        return {}
    rows = (await db.execute(
        select(FinanceCenterMumarenVoucherLineAuxiliary)
        .where(
            FinanceCenterMumarenVoucherLineAuxiliary.book_id == book_id,
            FinanceCenterMumarenVoucherLineAuxiliary.voucher_line_id.in_(line_ids),
        )
        .order_by(FinanceCenterMumarenVoucherLineAuxiliary.id)
    )).scalars().all()
    output: dict[int, list[FinanceCenterMumarenVoucherLineAuxiliary]] = {}
    for row in rows:
        output.setdefault(row.voucher_line_id, []).append(row)
    return output


async def _inherited_summaries(
    db: AsyncSession, voucher_ids: set[int],
) -> dict[int, str]:
    if not voucher_ids:
        return {}
    all_lines = (await db.execute(
        select(FinanceCenterMumarenVoucherLine)
        .where(FinanceCenterMumarenVoucherLine.voucher_id.in_(voucher_ids))
        .order_by(FinanceCenterMumarenVoucherLine.voucher_id, FinanceCenterMumarenVoucherLine.line_no)
    )).scalars().all()
    inherited: dict[int, str] = {}
    last_by_voucher: dict[int, str] = {}
    for line in all_lines:
        if line.summary:
            last_by_voucher[line.voucher_id] = line.summary
        inherited[line.id] = last_by_voucher.get(line.voucher_id, "")
    return inherited


@router.get("/vouchers/query", response_model=ApiResponse)
async def query_vouchers(
    book_id: int = Query(ge=1),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    status: Literal["draft", "reviewed", "posted"] | None = Query(default=None),
    voucher_type: str | None = Query(default=None, min_length=1, max_length=16),
    keyword: str | None = Query(default=None, max_length=500),
    account_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    filters = await _voucher_query_filters(
        db, book_id=book_id, status=status, date_from=date_from, date_to=date_to, period=period,
        voucher_type=voucher_type, keyword=keyword, account_id=account_id,
    )
    vouchers = (await db.execute(build_voucher_statement(filters).offset(offset).limit(limit))).scalars().all()
    total = int((await db.execute(build_voucher_count_statement(filters))).scalar_one())
    return ApiResponse.ok(data={"items": [_voucher_data(voucher) for voucher in vouchers], "total": total, "offset": offset, "limit": limit})


@router.get("/vouchers/query/lines", response_model=ApiResponse)
async def query_voucher_lines(
    book_id: int = Query(ge=1),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    status: Literal["draft", "reviewed", "posted"] | None = Query(default=None),
    voucher_type: str | None = Query(default=None, min_length=1, max_length=16),
    keyword: str | None = Query(default=None, max_length=500),
    account_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    filters = await _voucher_query_filters(
        db, book_id=book_id, status=status, date_from=date_from, date_to=date_to, period=period,
        voucher_type=voucher_type, keyword=keyword, account_id=account_id,
    )
    lines = (await db.execute(build_voucher_line_statement(filters).offset(offset).limit(limit))).scalars().all()
    total = int((await db.execute(build_voucher_line_count_statement(filters))).scalar_one())
    voucher_ids = {line.voucher_id for line in lines}
    account_ids = {line.account_id for line in lines}
    vouchers = (await db.execute(select(FinanceCenterMumarenVoucher).where(FinanceCenterMumarenVoucher.id.in_(voucher_ids)))).scalars().all() if voucher_ids else []
    accounts = (await db.execute(select(FinanceCenterMumarenAccount).where(
        FinanceCenterMumarenAccount.book_id == book_id,
        FinanceCenterMumarenAccount.id.in_(account_ids),
    ))).scalars().all() if account_ids else []
    voucher_by_id = {voucher.id: voucher for voucher in vouchers}
    account_by_id = {account.id: account for account in accounts}
    inherited = await _inherited_summaries(db, voucher_ids)
    auxiliaries = await _saved_auxiliaries_by_line(db, book_id=book_id, line_ids=[line.id for line in lines])
    items = [
        _voucher_line_query_data(
            line, voucher_by_id[line.voucher_id], account_by_id[line.account_id],
            inherited_summary=inherited.get(line.id, ""), auxiliaries=auxiliaries.get(line.id, []),
        )
        for line in lines
    ]
    return ApiResponse.ok(data={"items": items, "total": total, "offset": offset, "limit": limit})


@router.get("/vouchers/{voucher_id}/detail", response_model=ApiResponse)
async def get_voucher_detail(
    voucher_id: int,
    book_id: int = Query(ge=1),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    voucher = await db.get(FinanceCenterMumarenVoucher, voucher_id)
    if voucher is None or voucher.book_id != book_id:
        raise HTTPException(status_code=404, detail="凭证不属于所选账簿")
    line_accounts = (await db.execute(
        select(FinanceCenterMumarenVoucherLine, FinanceCenterMumarenAccount)
        .join(FinanceCenterMumarenAccount, FinanceCenterMumarenAccount.id == FinanceCenterMumarenVoucherLine.account_id)
        .where(
            FinanceCenterMumarenVoucherLine.voucher_id == voucher.id,
            FinanceCenterMumarenAccount.book_id == book_id,
        )
        .order_by(FinanceCenterMumarenVoucherLine.line_no)
    )).all()
    auxiliaries = await _saved_auxiliaries_by_line(
        db, book_id=book_id, line_ids=[line.id for line, _ in line_accounts],
    )
    return ApiResponse.ok(data=_voucher_detail_data(voucher, line_accounts, auxiliaries))


@router.get("/vouchers", response_model=ApiResponse)
async def get_vouchers(
    book_id: int | None = Query(default=None, ge=1),
    voucher_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    statement = select(FinanceCenterMumarenVoucher).order_by(FinanceCenterMumarenVoucher.id.desc())
    if book_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucher.book_id == book_id)
    if voucher_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucher.id == voucher_id)
    result = await db.execute(statement.offset(offset).limit(limit))
    return ApiResponse.ok(data=[_voucher_data(voucher) for voucher in result.scalars()])


@router.get("/vouchers/next-number", response_model=ApiResponse)
async def get_next_voucher_number(
    book_id: int = Query(ge=1),
    voucher_date: date = Query(...),
    voucher_type: str = Query(default="记", min_length=1, max_length=16),
    _: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    return ApiResponse.ok(data={"voucher_no": await next_voucher_number(
        db, book_id=book_id, voucher_date=voucher_date, voucher_type=voucher_type,
    )})


@router.get("/ledger/lines", response_model=ApiResponse)
async def get_ledger_lines(
    book_id: int = Query(ge=1),
    account_id: int | None = Query(default=None, ge=1),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    """Posted voucher lines for a single book; suitable for current and readonly history books."""
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    if account_id is not None:
        account = await db.get(FinanceCenterMumarenAccount, account_id)
        if account is None or account.book_id != book_id:
            raise HTTPException(status_code=404, detail="科目不属于所选账簿")
    order_columns = (
        FinanceCenterMumarenVoucher.voucher_date,
        FinanceCenterMumarenVoucher.id,
        FinanceCenterMumarenVoucherLine.line_no,
    )
    signed_amount = case(
        (FinanceCenterMumarenAccount.direction == "credit", FinanceCenterMumarenVoucherLine.credit_amount - FinanceCenterMumarenVoucherLine.debit_amount),
        else_=FinanceCenterMumarenVoucherLine.debit_amount - FinanceCenterMumarenVoucherLine.credit_amount,
    )
    running_balance = func.sum(signed_amount).over(
        partition_by=FinanceCenterMumarenVoucherLine.account_id,
        order_by=order_columns,
    ).label("running_balance")
    statement = (
        select(FinanceCenterMumarenVoucherLine, FinanceCenterMumarenVoucher, FinanceCenterMumarenAccount, running_balance)
        .join(FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucher.id == FinanceCenterMumarenVoucherLine.voucher_id)
        .join(FinanceCenterMumarenAccount, and_(
            FinanceCenterMumarenAccount.id == FinanceCenterMumarenVoucherLine.account_id,
            FinanceCenterMumarenAccount.book_id == FinanceCenterMumarenVoucher.book_id,
        ))
        .where(
            FinanceCenterMumarenVoucher.book_id == book_id,
            FinanceCenterMumarenVoucher.status == "posted",
        )
        .order_by(*order_columns)
        .limit(limit + 1)
        .offset(offset)
    )
    if account_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucherLine.account_id == account_id)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    if start_date:
        statement = statement.where(FinanceCenterMumarenVoucher.voucher_date >= start_date)
    if end_date:
        statement = statement.where(FinanceCenterMumarenVoucher.voucher_date <= end_date)
    result_rows = (await db.execute(statement)).all()
    has_more = len(result_rows) > limit
    rows = result_rows[:limit]
    voucher_ids = {voucher.id for _, voucher, _, _ in rows}
    inherited_summary_by_line: dict[int, str] = {}
    if voucher_ids:
        all_lines = (await db.execute(
            select(FinanceCenterMumarenVoucherLine)
            .where(FinanceCenterMumarenVoucherLine.voucher_id.in_(voucher_ids))
            .order_by(FinanceCenterMumarenVoucherLine.voucher_id, FinanceCenterMumarenVoucherLine.line_no)
        )).scalars().all()
        last_summary_by_voucher: dict[int, str] = {}
        for summary_line in all_lines:
            if summary_line.summary:
                last_summary_by_voucher[summary_line.voucher_id] = summary_line.summary
            if summary_line.id is not None:
                inherited_summary_by_line[summary_line.id] = last_summary_by_voucher.get(summary_line.voucher_id, "")
    output_rows = []
    for line, voucher, account, balance in rows:
        output_rows.append({
            "id": line.id, "voucher_id": voucher.id, "line_no": line.line_no,
            "voucher_no": voucher.voucher_no, "voucher_type": voucher.voucher_type,
            "voucher_date": voucher.voucher_date, "voucher_summary": voucher.summary,
            "line_summary": resolve_ledger_line_summary(
                line,
                inherited_summary=inherited_summary_by_line.get(line.id, ""),
                voucher_summary=voucher.summary,
            ),
            "account_id": account.id, "account_code": account.account_code,
            "account_name": account.account_name, "debit_amount": line.debit_amount,
            "credit_amount": line.credit_amount, "running_balance": balance,
            "balance_direction": account.direction, "is_readonly": voucher.is_readonly,
        })
    return ApiResponse.ok(data={"rows": output_rows, "has_more": has_more, "next_offset": offset + len(rows)})


def resolve_ledger_line_summary(line: FinanceCenterMumarenVoucherLine, *, inherited_summary: str, voucher_summary: str | None) -> str:
    """Keep an explicitly blank saved line blank; legacy blanks retain prior compatibility."""
    if line.summary_explicitly_cleared:
        return ""
    return line.summary or inherited_summary or voucher_summary or ""


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


@router.delete("/vouchers/{voucher_id}", response_model=ApiResponse)
async def delete_draft_voucher(
    voucher_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    voucher = await db.get(FinanceCenterMumarenVoucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if voucher.is_readonly:
        raise HTTPException(status_code=409, detail="历史只读凭证禁止删除")
    if voucher.status != "draft":
        raise HTTPException(status_code=409, detail="仅草稿凭证可删除")
    db.add(FinanceCenterMumarenAuditLog(
        book_id=voucher.book_id, voucher_id=voucher.id, action="delete_voucher",
        operator_id=_actor_id(current_user), detail=voucher.voucher_no,
    ))
    await db.delete(voucher)
    await db.flush()
    return ApiResponse.ok(data=None, message="草稿凭证已删除")


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


@router.get("/history/balance-snapshots", response_model=ApiResponse)
async def get_history_balance_snapshots(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: SysUser = Depends(require_mumaren_history_view),
    db: AsyncSession = Depends(get_db),
):
    """Readonly Kingdee source balances for reconciliation, never reporting."""
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    if not book.is_readonly:
        raise HTTPException(status_code=409, detail="余额快照仅适用于金蝶迁移只读账簿")
    statement = (
        select(FinanceCenterMumarenBalanceSnapshot, FinanceCenterMumarenAccount)
        .join(FinanceCenterMumarenAccount, and_(
            FinanceCenterMumarenAccount.id == FinanceCenterMumarenBalanceSnapshot.account_id,
            FinanceCenterMumarenAccount.book_id == FinanceCenterMumarenBalanceSnapshot.book_id,
        ))
        .where(FinanceCenterMumarenBalanceSnapshot.book_id == book_id)
        .order_by(FinanceCenterMumarenBalanceSnapshot.period_code.desc(), FinanceCenterMumarenAccount.account_code)
    )
    if period:
        statement = statement.where(FinanceCenterMumarenBalanceSnapshot.period_code == period)
    statement = statement.offset(offset).limit(limit)
    return ApiResponse.ok(data=[{
        "id": row.id, "period_code": row.period_code, "account_code": account.account_code,
        "account_name": account.account_name, "opening_amount": row.opening_amount,
        "period_debit": row.period_debit, "period_credit": row.period_credit,
        "closing_amount": row.closing_amount, "source_database": row.source_database,
        "is_readonly": row.is_readonly,
    } for row, account in (await db.execute(statement)).all()])


@router.get("/reports/trial-balance", response_model=ApiResponse)
async def get_trial_balance_report(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: SysUser = Depends(require_mumaren_voucher_view),
    db: AsyncSession = Depends(get_db),
):
    """当前账已过账凭证的科目余额与试算平衡；历史区不参与计算。"""
    try:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
        report = await get_trial_balance(
            db, book_id=book_id, period=period, start_date=start_date, end_date=end_date,
        )
        return ApiResponse.ok(data=await append_report_mapping_status(db, book_id=book_id, report=report))
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
        report = await get_profit_statement(db, book_id=book_id, period=period)
        return ApiResponse.ok(data=await append_report_mapping_status(db, book_id=book_id, report=report))
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
        report = await get_cash_flow_statement(db, book_id=book_id, period=period)
        return ApiResponse.ok(data=await append_report_mapping_status(db, book_id=book_id, report=report))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
