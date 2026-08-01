from pathlib import Path


VERSIONS = Path(__file__).parents[1] / "alembic" / "versions"


def _migration_text() -> str:
    matches = list(VERSIONS.glob("*_mumaren_finance_center_core.py"))
    assert len(matches) == 1, "牧马人财务中心必须有且仅有一个独立核心迁移"
    return matches[0].read_text(encoding="utf-8")


def test_mumaren_finance_center_migration_uses_an_isolated_schema_and_current_head():
    migration = _migration_text()

    assert 'down_revision: Union[str, None] = "e951b2d0a6c4"' in migration
    assert "CREATE SCHEMA IF NOT EXISTS finance_center_mumaren" in migration
    assert "DROP SCHEMA IF EXISTS finance_center_mumaren;" in migration
    assert "DROP SCHEMA IF EXISTS finance_center_mumaren CASCADE" not in migration
    assert "fin_current." not in migration
    assert "fin_history." not in migration
    assert "fin_read." not in migration
    assert "CREATE TABLE finance_center_mumaren.finance_center_mumaren_" in migration


def test_mumaren_finance_center_migration_creates_the_core_current_ledger_contract():
    migration = _migration_text()

    for table in (
        "finance_center_mumaren_books",
        "finance_center_mumaren_accounts",
        "finance_center_mumaren_fiscal_periods",
        "finance_center_mumaren_vouchers",
        "finance_center_mumaren_voucher_lines",
        "finance_center_mumaren_audit_logs",
    ):
        assert f"CREATE TABLE finance_center_mumaren.{table}" in migration

    assert "CHECK (status IN ('draft', 'reviewed', 'posted'))" in migration
    assert "ck_mumaren_finance_line_one_side" in migration
    assert "uq_mumaren_finance_voucher_no" in migration


def test_mumaren_finance_center_migration_makes_kingdee_history_readonly_and_idempotent():
    migration = _migration_text()

    for table in (
        "finance_center_mumaren_history_import_batches",
        "finance_center_mumaren_history_vouchers",
        "finance_center_mumaren_history_voucher_lines",
    ):
        assert f"CREATE TABLE finance_center_mumaren.{table}" in migration

    assert "source_system VARCHAR(32) NOT NULL DEFAULT 'kingdee'" in migration
    assert "record_type VARCHAR(32) NOT NULL DEFAULT 'historical'" in migration
    assert "is_readonly BOOLEAN NOT NULL DEFAULT true" in migration
    assert "source_key VARCHAR(256) NOT NULL" in migration
    assert "uq_mumaren_finance_history_batch" in migration
    assert "uq_mumaren_finance_history_voucher" in migration
    assert "uq_mumaren_finance_history_voucher_line" in migration
    assert "CHECK (is_readonly = true)" in migration


def test_mumaren_finance_center_migration_seeds_only_additive_finance_permissions():
    migration = _migration_text()

    assert "mumaren_finance_center:access" in migration
    assert "mumaren_finance_center:voucher:review" in migration
    assert "mumaren_finance_center:voucher:post" in migration
    assert "INSERT INTO" in migration
    assert "ON CONFLICT" in migration
    assert "DELETE FROM sys_role" not in migration
    assert "UPDATE sys_role" not in migration


def test_mumaren_finance_center_migration_records_its_own_permission_seeds_for_safe_downgrade():
    migration = _migration_text()

    assert "finance_center_mumaren_permission_seed_permissions" in migration
    assert "finance_center_mumaren_permission_seed_grants" in migration
    assert "RETURNING id" in migration
    assert "code LIKE 'mumaren_finance_center:%'" not in migration


def test_mumaren_finance_crud_migration_extends_the_merged_finance_center_chain():
    matches = list(VERSIONS.glob("*_persist_mumaren_finance_crud.py"))
    assert len(matches) == 1
    migration = matches[0].read_text(encoding="utf-8")

    # 财务核心与其他合法分支已由 217... 合并；CRUD 必须继承该 merge，不能
    # 重新从旧 a19... 分叉，避免 Alembic 再次产生多 head。
    assert "Revises: 217152ee1a62" in migration
    assert 'down_revision: Union[str, None] = "217152ee1a62"' in migration
    assert "a19c7e3d5b41" not in migration
