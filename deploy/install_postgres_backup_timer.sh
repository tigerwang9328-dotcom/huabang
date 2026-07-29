#!/usr/bin/env bash
# Installs a root-owned backup runner and a PostgreSQL-owned systemd timer.
# --apply is required because this changes systemd and removes the obsolete
# application-credential cron entry that cannot read Finance V2 schemas.
set -euo pipefail

readonly PROJECT_ROOT="${HUABANG_PROJECT_ROOT:-/srv/huabang-ai-center}"
readonly APP_USER="${HUABANG_APP_USER:-xiaohu}"
readonly SOURCE_BACKUP="$PROJECT_ROOT/deploy/pg_backup_as_postgres.sh"
readonly SOURCE_SERVICE="$PROJECT_ROOT/deploy/systemd/huabang-postgres-backup.service"
readonly SOURCE_TIMER="$PROJECT_ROOT/deploy/systemd/huabang-postgres-backup.timer"
readonly TARGET_DIR="/usr/local/lib/huabang"
readonly TARGET_BACKUP="$TARGET_DIR/pg_backup_as_postgres.sh"
readonly LEGACY_CRON_KEY="/scripts/pg_backup.sh"

apply=false
case "${1:-}" in
  "") ;;
  --apply) apply=true ;;
  --help|-h)
    echo "Usage: install_postgres_backup_timer.sh --apply"
    exit 0
    ;;
  *) echo "unknown argument: ${1}" >&2; exit 2 ;;
esac

[[ "$EUID" -eq 0 ]] || { echo "run as root via sudo" >&2; exit 2; }
for required in "$SOURCE_BACKUP" "$SOURCE_SERVICE" "$SOURCE_TIMER"; do
  [[ -f "$required" ]] || { echo "missing release asset: $required" >&2; exit 2; }
done
id "$APP_USER" >/dev/null

if [[ "$apply" != true ]]; then
  cat <<EOF
Would install root-owned backup runner: $TARGET_BACKUP
Would install systemd service/timer: huabang-postgres-backup.service/.timer
Would create PostgreSQL-owned backup directory: /var/backups/huabang-postgres
Would remove $APP_USER crontab entries containing: $LEGACY_CRON_KEY
EOF
  exit 0
fi

install -d -o root -g root -m 755 "$TARGET_DIR"
install -d -o postgres -g postgres -m 700 /var/backups/huabang-postgres
install -o root -g root -m 700 "$SOURCE_BACKUP" "$TARGET_BACKUP"
install -o root -g root -m 644 "$SOURCE_SERVICE" /etc/systemd/system/huabang-postgres-backup.service
install -o root -g root -m 644 "$SOURCE_TIMER" /etc/systemd/system/huabang-postgres-backup.timer

existing_crontab="$(runuser -u "$APP_USER" -- crontab -l 2>/dev/null || true)"
without_legacy_backup="$(printf '%s\n' "$existing_crontab" | awk -v key="$LEGACY_CRON_KEY" 'index($0, key) == 0 { print }')"
printf '%s\n' "$without_legacy_backup" | runuser -u "$APP_USER" -- crontab -

systemctl daemon-reload
systemctl enable --now huabang-postgres-backup.timer
echo "installed huabang-postgres-backup.timer and retired legacy application backup cron"
