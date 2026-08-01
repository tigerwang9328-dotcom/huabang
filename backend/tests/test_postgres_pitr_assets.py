from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def test_pitr_assets_archive_wal_and_schedule_physical_basebackups():
    archive_script = ROOT / "deploy" / "archive_postgres_wal.sh"
    basebackup_script = ROOT / "deploy" / "pg_basebackup_as_postgres.sh"
    config = ROOT / "deploy" / "postgresql" / "huabang-finance-pitr.conf"
    service = ROOT / "deploy" / "systemd" / "huabang-postgres-basebackup.service"
    timer = ROOT / "deploy" / "systemd" / "huabang-postgres-basebackup.timer"
    installer = ROOT / "deploy" / "install_postgres_pitr.sh"

    for path in (archive_script, basebackup_script, config, service, timer, installer):
        assert path.exists(), path
    for script in (archive_script, basebackup_script, installer):
        subprocess.run(["bash", "-n"], input=script.read_bytes(), check=True)

    archive_source = archive_script.read_text(encoding="utf-8")
    assert '[[ "$archive_name" != */* ]]' in archive_source
    assert "mv \"$archive_tmp\" \"$archive_target\"" in archive_source

    basebackup_source = basebackup_script.read_text(encoding="utf-8")
    assert "pg_basebackup" in basebackup_source
    assert "--wal-method=stream" in basebackup_source
    assert "WAL_KEEP_DAYS" in basebackup_source

    config_source = config.read_text(encoding="utf-8")
    assert "archive_mode = on" in config_source
    assert "archive_command" in config_source
    assert "archive_timeout = 900" in config_source

    service_source = service.read_text(encoding="utf-8")
    assert "User=postgres" in service_source
    assert "ReadWritePaths=/var/backups/huabang-postgres" in service_source
    assert "ProtectSystem=full" in service_source

    timer_source = timer.read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 01:30:00" in timer_source
    assert "Persistent=true" in timer_source

    installer_source = installer.read_text(encoding="utf-8")
    assert "--restart-postgresql" in installer_source
    assert "postgresql@16-main.service" in installer_source
    assert "systemctl enable --now huabang-postgres-basebackup.timer" in installer_source
