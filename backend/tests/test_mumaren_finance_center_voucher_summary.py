import os
from datetime import date
from decimal import Decimal

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.api.v1.mumaren_finance_center import _voucher_data
from app.models.mumaren_finance_center import FinanceCenterMumarenVoucher
from app.services.mumaren_finance_center.voucher_summary import (
    VoucherSummaryFilters,
    build_detail_statement,
    build_summary_statement,
    build_voucher_type_options_statement,
    normalize_voucher_type,
    serialize_summary_rows,
)


def test_voucher_payload_exposes_real_voucher_type_not_number_prefix():
    voucher = FinanceCenterMumarenVoucher(
        id=1,
        book_id=2,
        voucher_no="V-20260805-001",
        voucher_type="记",
        voucher_date=date(2026, 8, 5),
        status="posted",
        total_debit=Decimal("3.00"),
        total_credit=Decimal("3.00"),
    )
    assert _voucher_data(voucher)["voucher_type"] == "记"


def test_summary_rows_keep_real_type_and_mark_blank_type_unset():
    rows = serialize_summary_rows([
        {"period": "2026-08", "voucher_type": "记", "voucher_count": 1, "total_debit": Decimal("3.00"), "total_credit": Decimal("3.00")},
        {"period": "2026-08", "voucher_type": "", "voucher_count": 1, "total_debit": Decimal("2.00"), "total_credit": Decimal("2.00")},
    ])
    assert [row["voucher_type"] for row in rows] == ["记", "未设置"]
    assert rows[0]["voucher_type"] != "V"


def test_summary_statement_filters_by_book_status_period_type_and_keyword_without_limit():
    statement = build_summary_statement(VoucherSummaryFilters(
        book_id=9, status="posted", period="2026-08", voucher_type="记", keyword="V-20260805-001",
    ))
    sql = str(statement)
    assert "finance_center_mumaren_vouchers.book_id" in sql
    assert "finance_center_mumaren_vouchers.status" in sql
    assert "finance_center_mumaren_vouchers.voucher_type" in sql
    assert "voucher_no" in sql and "summary" in sql
    assert "LIMIT" not in sql.upper()


def test_detail_statement_is_paginated_after_the_same_filters():
    statement = build_detail_statement(
        VoucherSummaryFilters(book_id=9, status="reviewed", period="2026-08", voucher_type="收"), offset=20, limit=20,
    )
    sql = str(statement)
    assert "LIMIT" in sql.upper()
    assert "OFFSET" in sql.upper()


def test_blank_voucher_type_is_never_inferred_from_voucher_number():
    assert normalize_voucher_type("  ") == "未设置"
    assert normalize_voucher_type(None) == "未设置"


def test_voucher_type_options_project_their_sort_key_for_postgresql_distinct():
    statement = build_voucher_type_options_statement(VoucherSummaryFilters(book_id=9))
    assert "voucher_type_sort_rank" in str(statement)
