from pathlib import Path


def test_kingdee_three_book_migration_is_isolated_and_reversible():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "b19d3e5f7a01_add_mumaren_kingdee_three_book_migration.py"
    )

    assert migration.exists()
    content = migration.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "c1d2e3f4a5b7"' in content
    assert "finance_center_mumaren.finance_center_mumaren_kingdee_import_batches" in content
    assert "finance_center_mumaren.finance_center_mumaren_balance_snapshots" in content
    assert "UNIQUE(book_id, account_id, period_code)" not in content
    assert "UNIQUE(source_system, source_database, source_key)" in content
    assert "source_system = 'kingdee_history'" in content
    assert "CREATE TRIGGER" in content
    assert "DROP SCHEMA" not in content
    assert "fin_current" not in content
    assert "fin_history" not in content


def test_books_api_exposes_readonly_and_kingdee_source_metadata():
    api = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "mumaren_finance_center.py"
    content = api.read_text(encoding="utf-8")

    assert '"is_readonly": book.is_readonly' in content
    assert '"source_system": book.source_system' in content
    assert '"source_database": book.source_database' in content


def test_b20_upgrades_an_existing_legacy_b19_rehearsal_without_breaking_fresh_b19():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "b20f6a7d8e9f_upgrade_legacy_b19_kingdee_history_metadata.py"
    )

    assert migration.exists()
    content = migration.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "b19d3e5f7a01"' in content
    assert "DROP CONSTRAINT IF EXISTS uq_mumaren_finance_balance_snapshot" in content
    assert "source_payload -> 'source_balance'" in content
    assert "FDetailID" in content and "FCurrencyID" in content
    assert "source_system = 'kingdee_history'" in content
    assert "WHERE source_system = 'kingdee_history'" in content
    assert "SET LOCAL app.mumaren_kingdee_import = 'on';" in content
    assert content.index("SET LOCAL app.mumaren_kingdee_import = 'on';") < content.index(
        "UPDATE finance_center_mumaren.finance_center_mumaren_balance_snapshots"
    )
