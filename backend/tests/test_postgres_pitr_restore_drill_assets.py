from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def test_pitr_restore_drill_uses_an_isolated_socket_and_never_touches_production_data_dir():
    script = ROOT / "deploy" / "drill_postgres_pitr_restore.sh"
    installer = ROOT / "deploy" / "install_postgres_pitr.sh"

    assert script.exists()
    subprocess.run(["bash", "-n"], input=script.read_bytes(), check=True)

    source = script.read_text(encoding="utf-8")
    assert "recovery.signal" in source
    assert "restore_command" in source
    assert "pg_ctl" in source
    assert "--port" in source
    assert "pitr-drill-" in source
    assert "rm -rf \"$restore_dir\"" in source

    installer_source = installer.read_text(encoding="utf-8")
    assert "drill_postgres_pitr_restore.sh" in installer_source
