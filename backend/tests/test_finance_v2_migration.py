from pathlib import Path


def test_finance_v2_foundation_migration_is_isolated_and_append_only():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "7f4a8c1d9e20_finance_v2_current_core.py"
    migration = path.read_text(encoding="utf-8")

    assert 'down_revision = "6c1e4a7d2f09"' in migration
    assert "CREATE SCHEMA IF NOT EXISTS" not in migration
    assert "to_regnamespace('fin_current')" in migration
    assert "bootstrap_finance_database_roles.sql" in migration
    assert "CREATE TABLE fin_current.voucher" in migration
    assert "CREATE TABLE fin_current.operation_event" in migration
    assert "append-only" in migration
    assert "ck_fin_current_voucher_line_one_sided" not in migration


def test_profit_closing_evidence_migration_is_a_new_fin_current_fact_with_no_legacy_table_change():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "9c121d3145d9_add_finance_v2_profit_closing_evidence.py"
    migration = path.read_text(encoding="utf-8")

    assert "down_revision" in migration
    assert "CREATE TABLE fin_current.profit_closing_evidence" in migration
    assert "REFERENCES fin_current.voucher(id)" in migration
    assert "uq_fin_current_profit_close_period" in migration
    assert "DROP TABLE IF EXISTS fin_current.profit_closing_evidence" in migration
    assert "fin." not in migration.replace("fin_current.", "")


def test_history_migration_requires_bootstrapped_schemas_without_database_create_privilege():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "8c2b5e9f1a34_finance_v2_history_publication.py"
    migration = path.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS" not in migration
    assert "to_regnamespace('fin_history')" in migration
    assert "to_regnamespace('fin_read')" in migration
    assert "bootstrap_finance_database_roles.sql" in migration
