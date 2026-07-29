from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def test_backup_cron_installer_uses_an_app_writable_log_and_requires_apply_flag():
    script = ROOT / "deploy" / "install_pg_backup_cron.sh"

    assert script.exists()
    subprocess.run(["bash", "-n"], input=script.read_bytes(), check=True)

    source = script.read_text(encoding="utf-8")
    assert "--apply" in source
    assert '"$PROJECT_ROOT/logs/pg_backup.log"' in source
    assert "/usr/bin/flock -n /tmp/huabang_pg_backup.lock" in source
    assert 'crontab -' in source
    assert "/var/log/huabang_backup.log" not in source
