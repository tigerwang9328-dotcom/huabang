from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
DEPLOY = ROOT / "deploy"


def test_linux_release_entrypoint_is_syntax_valid_and_explicitly_read_only():
    script = DEPLOY / "release_finance_center_v2.sh"
    assert script.exists()
    subprocess.run(["bash", "-n"], input=script.read_bytes(), check=True)

    source = script.read_text(encoding="utf-8")
    for required in (
        "set -euo pipefail",
        "--execute",
        "--release-ref",
        "--history-manifest",
        "--history-manifest-sha256",
        "flock",
        "diff --quiet",
        "rev-parse --verify",
        "GIT_TERMINAL_PROMPT=0",
        "BatchMode=yes",
        "pg_dump",
        "bootstrap_finance_database_roles.sql",
        "postgres_sql \"$(<\"$BACKEND_DIR/scripts/bootstrap_finance_database_roles.sql\")\"",
        "fin_migrator",
        "fin_history_importer",
        "FINANCE_DB_USER",
        "PYTHONPATH",
        "seed_finance_v2_permissions.py",
        "import_finance_v2_history.py",
        "verify_finance_center_v2.py",
        "systemctl restart huabang-backend.service",
        "rollback_runtime",
    ):
        assert required in source
    assert "draft_enabled" in source
    assert "review_enabled" in source
    assert "post_enabled" in source
    assert "--no-verify" not in source


def test_release_verifier_checks_fin_app_history_visibility_and_closed_write_gates():
    verifier = DEPLOY / "verify_finance_center_v2.py"
    assert verifier.exists()
    source = verifier.read_text(encoding="utf-8")
    for required in (
        "FINANCE_DATABASE_URL",
        "current_user",
        "fin_read.history_voucher",
        "fin_current.feature_gate",
        "draft_enabled",
        "review_enabled",
        "post_enabled",
        "expected_history_vouchers",
        "expected_history_entries",
    ):
        assert required in source


def test_powershell_entrypoint_only_orchestrates_the_remote_linux_release_script():
    script = DEPLOY / "release_finance_center_v2.ps1"
    assert script.exists()
    source = script.read_text(encoding="utf-8")
    assert "ssh" in source
    assert "-o BatchMode=yes" in source
    assert "release_finance_center_v2.sh" in source
    assert "sudo" not in source


def test_legacy_database_operational_scripts_load_credentials_from_the_private_environment_file():
    for filename in (
        "health_check.sh",
        "pg_backup.sh",
        "rebuild_pos_sale_goods_from_tickets.sh",
        "sync_pos_tickets_daily.sh",
    ):
        script = ROOT / "scripts" / filename
        subprocess.run(["bash", "-n"], input=script.read_bytes(), check=True)
        source = script.read_text(encoding="utf-8")
        assert "PGPASSFILE" in source
        assert "DB_PASSWORD" in source
        assert ("huabang" + "2024") not in source
