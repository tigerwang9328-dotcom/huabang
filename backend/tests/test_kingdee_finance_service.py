from decimal import Decimal

from app.services.kingdee_finance_service import (
    EXPECTED_ACCOUNT_SET_TOTALS,
    EXPECTED_SNAPSHOT_TOTALS,
    build_source_pk,
    evaluate_statement_status,
    validate_snapshot,
    validate_account_set_snapshots,
    validate_balance_equations,
    validate_voucher_header_totals,
    validate_voucher_balances,
)


def test_snapshot_validation_accepts_the_verified_three_account_set_baseline():
    result = validate_snapshot(EXPECTED_SNAPSHOT_TOTALS.copy())

    assert result["status"] == "ready"
    assert result["errors"] == []


def test_snapshot_validation_blocks_any_baseline_count_difference():
    totals = EXPECTED_SNAPSHOT_TOTALS.copy()
    totals["voucher_entries"] -= 1

    result = validate_snapshot(totals)

    assert result["status"] == "blocked"
    assert "voucher_entries" in result["errors"][0]


def test_voucher_balance_validation_reports_unbalanced_source_voucher():
    rows = [
        {"account_set": "AIS1", "voucher_id": "9", "debit": Decimal("10.00"), "credit": Decimal("0")},
        {"account_set": "AIS1", "voucher_id": "9", "debit": Decimal("0"), "credit": Decimal("9.99")},
    ]

    errors = validate_voucher_balances(rows)

    assert errors == [{
        "account_set": "AIS1",
        "voucher_id": "9",
        "debit": "10.00",
        "credit": "9.99",
        "difference": "0.01",
    }]


def test_statement_status_never_presents_unmapped_or_absent_data_as_ready():
    assert evaluate_statement_status(source_rows=0, account_count=10, mapped_count=10) == "pending_data"
    assert evaluate_statement_status(source_rows=20, account_count=10, mapped_count=9) == "pending_mapping"
    assert evaluate_statement_status(source_rows=20, account_count=10, mapped_count=10) == "ready"


def test_source_pk_is_stable_and_explicitly_names_the_account_set():
    assert build_source_pk("AIS20260305112309", 12, 3) == "AIS20260305112309:12:3"


def test_each_official_account_set_must_match_its_own_verified_baseline():
    result = validate_account_set_snapshots({key: value.copy() for key, value in EXPECTED_ACCOUNT_SET_TOTALS.items()})
    assert result == {"status": "ready", "errors": []}

    changed = {key: value.copy() for key, value in EXPECTED_ACCOUNT_SET_TOTALS.items()}
    changed["AIS20260305112309"]["vouchers"] -= 1
    assert validate_account_set_snapshots(changed)["status"] == "blocked"


def test_voucher_header_totals_must_equal_entry_totals():
    headers = [{"account_set": "AIS1", "voucher_id": "1", "debit": "10", "credit": "10"}]
    entries = [
        {"account_set": "AIS1", "voucher_id": "1", "debit": "10", "credit": "0"},
        {"account_set": "AIS1", "voucher_id": "1", "debit": "0", "credit": "9"},
    ]
    errors = validate_voucher_header_totals(headers, entries)
    assert errors[0]["credit_difference"] == "1.00"


def test_opening_plus_activity_must_equal_closing_balance():
    errors = validate_balance_equations([{
        "account_set": "AIS1", "source_pk": "row-1",
        "opening_debit": "10", "opening_credit": "0",
        "period_debit": "5", "period_credit": "2",
        "closing_debit": "12", "closing_credit": "0",
    }])
    assert errors[0]["difference"] == "1.00"
