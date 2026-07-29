from pathlib import Path

from app.models.finance_v2 import (
    FinanceV2AccountingBook,
    FinanceV2CommandIdempotency,
    FinanceV2LedgerBalance,
    FinanceV2Voucher,
    FinanceV2VoucherLine,
)
from app.models.finance_v2_operations import FinanceV2VoucherNumberCounter, FinanceV2VoucherNumberReservation


def test_current_finance_tables_are_isolated_from_legacy_fin_schema():
    assert FinanceV2AccountingBook.__table__.schema == "fin_current"
    assert FinanceV2Voucher.__table__.schema == "fin_current"
    assert FinanceV2VoucherLine.__table__.schema == "fin_current"
    assert FinanceV2LedgerBalance.__table__.schema == "fin_current"


def test_voucher_persistence_carries_review_post_and_optimistic_lock_fields():
    names = set(FinanceV2Voucher.__table__.c.keys())

    assert {"status", "version", "prepared_by", "reviewer_id", "approved_by", "posted_by", "request_id"} <= names
    constraints = " ".join(str(item.sqltext) for item in FinanceV2Voucher.__table__.constraints if hasattr(item, "sqltext"))
    assert "submitted" in constraints
    assert "reviewing" in constraints
    assert "approved" in constraints
    assert "posted" in constraints


def test_voucher_line_and_command_idempotency_have_database_identity_guards():
    line_constraint_names = {item.name for item in FinanceV2VoucherLine.__table__.constraints}
    command_constraint_names = {item.name for item in FinanceV2CommandIdempotency.__table__.constraints}

    assert "ck_fin_current_voucher_line_nonnegative" in line_constraint_names
    assert "ck_fin_current_voucher_line_one_sided" not in line_constraint_names
    assert "uq_fin_current_command_scope_key" in command_constraint_names


def test_voucher_line_rejects_simultaneous_positive_debit_and_credit_in_model_and_migration():
    constraint_names = {item.name for item in FinanceV2VoucherLine.__table__.constraints}
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "alembic" / "versions").glob("*.py")
    )

    assert "ck_fin_current_voucher_line_not_both_positive" in constraint_names
    assert "ck_fin_current_voucher_line_not_both_positive" in migration_sources


def test_voucher_number_counter_and_reservation_preserve_period_scoped_audit_identity():
    counter_constraints = {item.name for item in FinanceV2VoucherNumberCounter.__table__.constraints}
    reservation_constraints = {item.name for item in FinanceV2VoucherNumberReservation.__table__.constraints}

    assert FinanceV2VoucherNumberCounter.__table__.schema == "fin_current"
    assert FinanceV2VoucherNumberReservation.__table__.schema == "fin_current"
    assert "uq_fin_current_voucher_number_counter_scope" in counter_constraints
    assert "uq_fin_current_voucher_number_reservation_scope" in reservation_constraints
    assert "voided" in " ".join(
        str(item.sqltext) for item in FinanceV2VoucherNumberReservation.__table__.constraints if hasattr(item, "sqltext")
    )
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "alembic" / "versions").glob("*.py")
    )
    assert "fin_current.voucher_number_counter" in migration_sources
    assert "fin_current.voucher_number_reservation" in migration_sources


def test_operation_events_have_a_database_level_immutability_guard():
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "alembic" / "versions").glob("*.py")
    )

    assert "tr_fin_current_operation_event_immutable" in migration_sources
    assert "operation_event records are append-only" in migration_sources
