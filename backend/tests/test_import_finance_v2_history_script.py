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


def test_history_import_dry_run_does_not_eagerly_load_database_settings():
    source = SCRIPT.read_text(encoding="utf-8")
    before_execute = source.split("async def _execute", maxsplit=1)[0]

    assert "from app.core.database import AsyncSessionLocal" not in before_execute
    assert "from app.services.finance_v2.history_import_service" not in before_execute
    assert "from app.services.finance_v2.history_import_plan import HistoryPublicationError, plan_history_import" in before_execute
    assert "from app.core.database import AsyncSessionLocal" in source
