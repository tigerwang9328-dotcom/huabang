from pathlib import Path


def test_finance_v2_foundation_migration_is_isolated_and_append_only():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "7f4a8c1d9e20_finance_v2_current_core.py"
    migration = path.read_text(encoding="utf-8")

    assert 'down_revision = "6c1e4a7d2f09"' in migration
    assert "CREATE SCHEMA IF NOT EXISTS fin_current" in migration
    assert "CREATE TABLE fin_current.voucher" in migration
    assert "CREATE TABLE fin_current.operation_event" in migration
    assert "append-only" in migration
    assert "ck_fin_current_voucher_line_one_sided" not in migration
