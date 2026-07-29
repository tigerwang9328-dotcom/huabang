from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "import_finance_v2_history.py"


def test_finance_v2_history_import_script_is_dry_run_by_default_and_requires_dedicated_role():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'parser.add_argument("--execute", action="store_true")' in source
    assert 'parser.add_argument("--publish", action="store_true")' in source
    assert 'if not args.execute:' in source
    assert 'current_user != "fin_history_importer"' in source
    assert 'sys.path.insert(0, str(Path(__file__).resolve().parents[1]))' in source
    assert "FinanceV2HistoryImportService" in source
