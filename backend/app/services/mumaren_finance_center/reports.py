"""牧马人财务中心的独立账簿与报表服务。

所有查询只针对 ``finance_center_mumaren`` 当前账表，且仅统计已人工过账
的凭证；历史金蝶归档表和华邦既有财务表均不参与计算。
"""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


_ZERO = Decimal("0")


def _value(row: Mapping[str, Any] | object, name: str, default: Any = None) -> Any:
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


def _amount(row: Mapping[str, Any] | object, name: str) -> Decimal:
    return Decimal(str(_value(row, name, _ZERO) or _ZERO))


def _account_row(account: FinanceCenterMumarenAccount | object, debit: Decimal, credit: Decimal) -> dict:
    direction = _value(account, "direction", "debit")
    net = debit - credit if direction == "debit" else credit - debit
    closing_debit = max(net, _ZERO) if direction == "debit" else max(-net, _ZERO)
    closing_credit = max(-net, _ZERO) if direction == "debit" else max(net, _ZERO)
    return {
        "account_id": _value(account, "id"),
        "account_code": _value(account, "account_code"),
        "account_name": _value(account, "account_name"),
        "direction": direction,
        "debit_amount": debit,
        "credit_amount": credit,
        "closing_debit": closing_debit,
        "closing_credit": closing_credit,
    }


def _totals_by_account(lines: Iterable[Mapping[str, Any] | object]) -> dict[int, tuple[Decimal, Decimal]]:
    totals: dict[int, tuple[Decimal, Decimal]] = {}
    for line in lines:
        account_id = _value(line, "account_id")
        if account_id is None:
            continue
        debit, credit = totals.get(account_id, (_ZERO, _ZERO))
        totals[account_id] = (debit + _amount(line, "debit_amount"), credit + _amount(line, "credit_amount"))
    return totals


def build_trial_balance(
    accounts: Sequence[FinanceCenterMumarenAccount | object],
    posted_lines: Iterable[Mapping[str, Any] | object],
) -> dict:
    """按当前账已过账分录生成科目余额及试算平衡。"""
    totals = _totals_by_account(posted_lines)
    rows = []
    for account in sorted(accounts, key=lambda item: str(_value(item, "account_code", ""))):
        debit, credit = totals.get(_value(account, "id"), (_ZERO, _ZERO))
        rows.append(_account_row(account, debit, credit))
    total_debit = sum((row["debit_amount"] for row in rows), _ZERO)
    total_credit = sum((row["credit_amount"] for row in rows), _ZERO)
    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
    }


def build_profit_statement(
    accounts: Sequence[FinanceCenterMumarenAccount | object],
    posted_lines: Iterable[Mapping[str, Any] | object],
) -> dict:
    """按收入贷减借、费用借减贷计算利润表；没有当前账即返回全零。"""
    totals = _totals_by_account(posted_lines)
    income_rows: list[dict] = []
    expense_rows: list[dict] = []
    for account in sorted(accounts, key=lambda item: str(_value(item, "account_code", ""))):
        debit, credit = totals.get(_value(account, "id"), (_ZERO, _ZERO))
        account_type = _value(account, "account_type")
        base = {
            "account_id": _value(account, "id"),
            "account_code": _value(account, "account_code"),
            "account_name": _value(account, "account_name"),
        }
        if account_type == "income":
            income_rows.append({**base, "amount": credit - debit})
        elif account_type == "expense":
            expense_rows.append({**base, "amount": debit - credit})
    total_income = sum((row["amount"] for row in income_rows), _ZERO)
    total_expense = sum((row["amount"] for row in expense_rows), _ZERO)
    return {
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": total_income - total_expense,
    }


def _period_bounds(period: str | None) -> tuple[date | None, date | None]:
    if period is None:
        return None, None
    try:
        year, month = (int(part) for part in period.split("-", 1))
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError) as error:
        raise ValueError("期间必须是 YYYY-MM") from error


async def _load_posted_book_data(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> tuple[list[FinanceCenterMumarenAccount], list[FinanceCenterMumarenVoucherLine]]:
    """读取新 schema 当前账：仅已过账凭证，绝不触碰历史或旧财务对象。"""
    accounts_result = await db.execute(
        select(FinanceCenterMumarenAccount)
        .where(
            FinanceCenterMumarenAccount.book_id == book_id,
            FinanceCenterMumarenAccount.is_active.is_(True),
        )
        .order_by(FinanceCenterMumarenAccount.account_code)
    )
    start_date, end_date = _period_bounds(period)
    statement = (
        select(FinanceCenterMumarenVoucherLine)
        .join(
            FinanceCenterMumarenVoucher,
            FinanceCenterMumarenVoucherLine.voucher_id == FinanceCenterMumarenVoucher.id,
        )
        .where(
            FinanceCenterMumarenVoucher.book_id == book_id,
            FinanceCenterMumarenVoucher.status == "posted",
        )
        .order_by(FinanceCenterMumarenVoucher.voucher_date, FinanceCenterMumarenVoucherLine.line_no)
    )
    if start_date is not None and end_date is not None:
        statement = statement.where(FinanceCenterMumarenVoucher.voucher_date.between(start_date, end_date))
    lines_result = await db.execute(statement)
    return list(accounts_result.scalars()), list(lines_result.scalars())


async def get_trial_balance(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> dict:
    accounts, posted_lines = await _load_posted_book_data(db, book_id=book_id, period=period)
    return build_trial_balance(accounts, posted_lines)


async def get_profit_statement(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> dict:
    accounts, posted_lines = await _load_posted_book_data(db, book_id=book_id, period=period)
    return build_profit_statement(accounts, posted_lines)
