from pathlib import Path


def test_reset_tool_requires_explicit_test_database_and_defaults_to_dry_run():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "reset_kingdee_three_book_rehearsal.py"
    )
    source = script.read_text(encoding="utf-8")

    assert 'parser.add_argument("--database-name", required=True' in source
    assert 'APPROVED_REHEARSAL_DATABASES = frozenset({"huabang_ai_finance_drill_20260729_r2"})' in source
    assert "database_name not in APPROVED_REHEARSAL_DATABASES" in source
    assert 'parser.add_argument("--execute", action="store_true"' in source
    assert 'current_database()' in source
    assert "SET TRANSACTION READ ONLY" in source
    assert source.index('SET TRANSACTION READ ONLY') < source.index('SELECT current_database()')
    assert "SET LOCAL app.mumaren_kingdee_import = 'on'" in source
    assert "kingdee_finance" not in source
    assert "fin_history" not in source


def test_reset_tool_removes_only_three_readonly_kingdee_books_and_related_rows():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "reset_kingdee_three_book_rehearsal.py"
    )
    source = script.read_text(encoding="utf-8")

    assert "EXPECTED_BOOK_COUNT = 3" in source
    assert "len(batch_keys) != 1" in source
    assert 'source_system == "kingdee_history"' in source
    assert "is_readonly.is_(True)" in source
    assert "FinanceCenterMumarenBalanceSnapshot" in source
    assert "FinanceCenterMumarenVoucherLine" in source
    assert "FinanceCenterMumarenVoucher" in source
    assert "FinanceCenterMumarenFiscalPeriod" in source
    assert "FinanceCenterMumarenAccount" in source
    assert "FinanceCenterMumarenBook" in source
