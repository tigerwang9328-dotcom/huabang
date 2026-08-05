"""Server-side voucher summary queries for the independent finance centre."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, func, or_, select
from sqlalchemy.sql import Select

from app.models.mumaren_finance_center import FinanceCenterMumarenVoucher


VoucherStatus = Literal["draft", "reviewed", "posted"]
UNSET_VOUCHER_TYPE = "未设置"


@dataclass(frozen=True)
class VoucherSummaryFilters:
    book_id: int
    status: VoucherStatus = "posted"
    period: str | None = None
    voucher_type: str | None = None
    keyword: str | None = None


def normalize_voucher_type(value: object) -> str:
    text = str(value or "").strip()
    return text or UNSET_VOUCHER_TYPE


def _period_expression():
    return func.to_char(FinanceCenterMumarenVoucher.voucher_date, "YYYY-MM")


def _voucher_type_expression():
    return func.coalesce(
        func.nullif(func.trim(FinanceCenterMumarenVoucher.voucher_type), ""),
        UNSET_VOUCHER_TYPE,
    )


def _voucher_type_rank(voucher_type):
    return case(
        (voucher_type == "记", 1), (voucher_type == "收", 2), (voucher_type == "付", 3),
        (voucher_type == "转", 4), else_=5,
    )


def _where(filters: VoucherSummaryFilters, *, include_period: bool = True, include_voucher_type: bool = True):
    clauses = [
        FinanceCenterMumarenVoucher.book_id == filters.book_id,
        FinanceCenterMumarenVoucher.status == filters.status,
    ]
    if include_period and filters.period:
        clauses.append(_period_expression() == filters.period)
    if include_voucher_type and filters.voucher_type:
        clauses.append(_voucher_type_expression() == normalize_voucher_type(filters.voucher_type))
    if filters.keyword and filters.keyword.strip():
        needle = f"%{filters.keyword.strip()}%"
        clauses.append(or_(
            FinanceCenterMumarenVoucher.voucher_no.ilike(needle),
            FinanceCenterMumarenVoucher.summary.ilike(needle),
        ))
    return clauses


def build_summary_statement(filters: VoucherSummaryFilters) -> Select:
    period = _period_expression().label("period")
    voucher_type = _voucher_type_expression().label("voucher_type")
    rank = _voucher_type_rank(voucher_type)
    return (
        select(
            period,
            voucher_type,
            func.count(FinanceCenterMumarenVoucher.id).label("voucher_count"),
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_debit), 0).label("total_debit"),
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_credit), 0).label("total_credit"),
        )
        .where(*_where(filters))
        .group_by(period, voucher_type)
        .order_by(period.desc(), rank, voucher_type)
    )


def build_period_options_statement(filters: VoucherSummaryFilters) -> Select:
    period = _period_expression().label("period")
    return select(period).where(*_where(filters, include_period=False, include_voucher_type=False)).distinct().order_by(period.desc())


def build_voucher_type_options_statement(filters: VoucherSummaryFilters) -> Select:
    voucher_type = _voucher_type_expression().label("voucher_type")
    options = (
        select(voucher_type, _voucher_type_rank(voucher_type).label("voucher_type_sort_rank"))
        .where(*_where(filters, include_voucher_type=False))
        .group_by(voucher_type)
        .subquery()
    )
    return select(options.c.voucher_type).order_by(options.c.voucher_type_sort_rank, options.c.voucher_type)


def build_detail_statement(filters: VoucherSummaryFilters, *, offset: int, limit: int) -> Select:
    return (
        select(FinanceCenterMumarenVoucher)
        .where(*_where(filters))
        .order_by(FinanceCenterMumarenVoucher.voucher_date.desc(), FinanceCenterMumarenVoucher.id.desc())
        .offset(offset)
        .limit(limit)
    )


def build_detail_count_statement(filters: VoucherSummaryFilters) -> Select:
    return select(func.count(FinanceCenterMumarenVoucher.id)).where(*_where(filters))


def serialize_summary_rows(rows: list[dict]) -> list[dict]:
    return [{
        "period": str(row["period"]),
        "voucher_type": normalize_voucher_type(row["voucher_type"]),
        "voucher_count": int(row["voucher_count"] or 0),
        "total_debit": float(row["total_debit"] or 0),
        "total_credit": float(row["total_credit"] or 0),
        "is_balanced": (row["total_debit"] or 0) == (row["total_credit"] or 0),
    } for row in rows]
