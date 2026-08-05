"""Read-only voucher and voucher-line query statements."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.sql import Select

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


VoucherStatus = Literal["draft", "reviewed", "posted"]


@dataclass(frozen=True)
class VoucherQueryFilters:
    book_id: int
    status: VoucherStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
    period: str | None = None
    voucher_type: str | None = None
    keyword: str | None = None
    account_id: int | None = None


def _where(filters: VoucherQueryFilters, *, include_account: bool = True):
    clauses = [FinanceCenterMumarenVoucher.book_id == filters.book_id]
    if filters.status:
        clauses.append(FinanceCenterMumarenVoucher.status == filters.status)
    if filters.date_from:
        clauses.append(FinanceCenterMumarenVoucher.voucher_date >= filters.date_from)
    if filters.date_to:
        clauses.append(FinanceCenterMumarenVoucher.voucher_date <= filters.date_to)
    if filters.period:
        clauses.append(func.to_char(FinanceCenterMumarenVoucher.voucher_date, "YYYY-MM") == filters.period)
    if filters.voucher_type and filters.voucher_type.strip():
        clauses.append(FinanceCenterMumarenVoucher.voucher_type == filters.voucher_type.strip())
    if filters.keyword and filters.keyword.strip():
        needle = f"%{filters.keyword.strip()}%"
        clauses.append(or_(
            FinanceCenterMumarenVoucher.voucher_no.ilike(needle),
            FinanceCenterMumarenVoucher.summary.ilike(needle),
        ))
    if include_account and filters.account_id is not None:
        clauses.append(FinanceCenterMumarenVoucher.id.in_(
            select(FinanceCenterMumarenVoucherLine.voucher_id).where(
                FinanceCenterMumarenVoucherLine.account_id == filters.account_id,
            )
        ))
    return clauses


def build_voucher_statement(filters: VoucherQueryFilters) -> Select:
    return select(FinanceCenterMumarenVoucher).where(*_where(filters)).order_by(
        FinanceCenterMumarenVoucher.voucher_date.desc(), FinanceCenterMumarenVoucher.id.desc(),
    )


def build_voucher_count_statement(filters: VoucherQueryFilters) -> Select:
    return select(func.count(FinanceCenterMumarenVoucher.id)).where(*_where(filters))


def build_voucher_line_statement(filters: VoucherQueryFilters) -> Select:
    statement = (
        select(FinanceCenterMumarenVoucherLine)
        .join(FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucher.id == FinanceCenterMumarenVoucherLine.voucher_id)
        .where(*_where(filters, include_account=False))
        .order_by(
            FinanceCenterMumarenVoucher.voucher_date.desc(),
            FinanceCenterMumarenVoucher.id.desc(),
            FinanceCenterMumarenVoucherLine.line_no,
        )
    )
    if filters.account_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucherLine.account_id == filters.account_id)
    return statement


def build_voucher_line_count_statement(filters: VoucherQueryFilters) -> Select:
    statement = (
        select(func.count(FinanceCenterMumarenVoucherLine.id))
        .join(FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucher.id == FinanceCenterMumarenVoucherLine.voucher_id)
        .where(*_where(filters, include_account=False))
    )
    if filters.account_id is not None:
        statement = statement.where(FinanceCenterMumarenVoucherLine.account_id == filters.account_id)
    return statement
