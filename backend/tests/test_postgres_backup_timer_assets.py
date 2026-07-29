from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def test_postgres_backup_timer_runs_a_root_owned_template_as_postgres():
    backup_script = ROOT / "deploy" / "pg_backup_as_postgres.sh"
    service = ROOT / "deploy" / "systemd" / "huabang-postgres-backup.service"
    timer = ROOT / "deploy" / "systemd" / "huabang-postgres-backup.timer"
    installer = ROOT / "deploy" / "install_postgres_backup_timer.sh"

    for path in (backup_script, service, timer, installer):
        assert path.exists(), path
    subprocess.run(["bash", "-n"], input=backup_script.read_bytes(), check=True)
    subprocess.run(["bash", "-n"], input=installer.read_bytes(), check=True)

    backup_source = backup_script.read_text(encoding="utf-8")
    assert "pg_dump -Fc" in backup_source
    assert "sha256sum" in backup_source
    assert "KEEP_DAYS" in backup_source
    assert "DB_PASSWORD" not in backup_source

    service_source = service.read_text(encoding="utf-8")
    assert "User=postgres" in service_source
    assert "ProtectSystem=full" in service_source
    assert "ReadWritePaths=/var/backups/huabang-postgres" in service_source

    timer_source = timer.read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 03,15:00:00" in timer_source
    assert "Persistent=true" in timer_source

    installer_source = installer.read_text(encoding="utf-8")
    assert "--apply" in installer_source
    assert "install -o root -g root -m 700" in installer_source
    assert "systemctl enable --now huabang-postgres-backup.timer" in installer_source
    assert "crontab -" in installer_source
