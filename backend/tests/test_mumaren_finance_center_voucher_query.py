import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.api.v1.mumaren_finance_center import (
    _voucher_query_filters,
    _voucher_detail_data,
    _voucher_line_query_data,
    get_voucher_detail,
    validate_voucher_query_dates,
)
from app.models.mumaren_finance_center import FinanceCenterMumarenAccount, FinanceCenterMumarenBook, FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucherLine
from app.services.mumaren_finance_center.voucher_query import VoucherQueryFilters, build_voucher_line_statement, build_voucher_statement


def _voucher(*, book_id=7, readonly=False):
    return FinanceCenterMumarenVoucher(
        id=11, book_id=book_id, voucher_no="记-001", voucher_type="记", voucher_date=date(2026, 8, 5),
        summary="总摘要", status="posted", total_debit=Decimal("12.00"), total_credit=Decimal("12.00"),
        source_system="kingdee_history" if readonly else None, source_database="K3_2024" if readonly else None,
        is_readonly=readonly, is_normalized=readonly,
    )


class FakeDb:
    def __init__(self, *records):
        self.records = {(type(record), record.id): record for record in records}

    async def get(self, model, record_id):
        return self.records.get((model, record_id))


def test_query_filters_scope_book_status_date_type_keyword_and_account_without_any_500_cap():
    filters = VoucherQueryFilters(
        book_id=7, status="posted", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        voucher_type="记", keyword="总摘要", account_id=19,
    )
    header_sql = str(build_voucher_statement(filters))
    line_sql = str(build_voucher_line_statement(filters))
    for sql in (header_sql, line_sql):
        assert "finance_center_mumaren_vouchers.book_id" in sql
        assert "finance_center_mumaren_vouchers.status" in sql
        assert "voucher_date" in sql
        assert "voucher_type" in sql
        assert "voucher_no" in sql and "summary" in sql
    assert "account_id" in line_sql
    assert "LIMIT" not in header_sql.upper()


def test_date_range_and_period_are_mutually_exclusive():
    with pytest.raises(ValueError, match="期间"):
        validate_voucher_query_dates(date(2026, 8, 1), None, "2026-08")
    with pytest.raises(ValueError, match="开始日期"):
        validate_voucher_query_dates(date(2026, 8, 2), date(2026, 8, 1), None)


@pytest.mark.asyncio
async def test_query_rejects_account_from_another_book_before_building_a_statement():
    book = FinanceCenterMumarenBook(id=7, book_code="B7", book_name="账簿7", status="active", is_readonly=False)
    foreign_account = FinanceCenterMumarenAccount(id=19, book_id=8, account_code="1001", account_name="库存现金")
    with pytest.raises(Exception) as error:
        await _voucher_query_filters(
            FakeDb(book, foreign_account), book_id=7, status=None, date_from=None, date_to=None,
            period=None, voucher_type=None, keyword=None, account_id=19,
        )
    assert getattr(error.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_detail_rejects_a_voucher_id_from_another_book():
    book = FinanceCenterMumarenBook(id=7, book_code="B7", book_name="账簿7", status="active", is_readonly=False)
    foreign_voucher = _voucher(book_id=8)
    with pytest.raises(Exception) as error:
        await get_voucher_detail(voucher_id=foreign_voucher.id, book_id=7, _=None, db=FakeDb(book, foreign_voucher))
    assert getattr(error.value, "status_code", None) == 404


def test_line_result_uses_saved_auxiliaries_only_and_reuses_effective_summary():
    voucher = _voucher()
    account = FinanceCenterMumarenAccount(id=19, book_id=7, account_code="1001", account_name="库存现金")
    line = FinanceCenterMumarenVoucherLine(id=31, voucher_id=11, line_no=2, account_id=19, summary=None, debit_amount=Decimal("12.00"), credit_amount=Decimal("0"))
    row = _voucher_line_query_data(line, voucher, account, inherited_summary="上一行摘要", auxiliaries=[])
    assert row["line_summary"] == "上一行摘要"
    assert row["auxiliaries"] == "—"
    assert row["status"] == "posted"


def test_detail_exposes_complete_lines_totals_balance_and_history_flags():
    voucher = _voucher(readonly=True)
    account = FinanceCenterMumarenAccount(id=19, book_id=7, account_code="1001", account_name="库存现金")
    line = FinanceCenterMumarenVoucherLine(id=31, voucher_id=11, line_no=1, account_id=19, summary="已保存摘要", debit_amount=Decimal("12.00"), credit_amount=Decimal("0"))
    detail = _voucher_detail_data(voucher, [(line, account)], {31: []})
    assert detail["is_balanced"] is True
    assert detail["total_debit"] == Decimal("12.00")
    assert detail["lines"][0]["line_summary"] == "已保存摘要"
    assert detail["is_readonly"] is True
    assert detail["source_database"] == "K3_2024"
