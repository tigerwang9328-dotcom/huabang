#!/usr/bin/env bash
# Install the daily logical PostgreSQL backup as the application owner.
# It is deliberately opt-in: inspect the rendered crontab first, then pass
# --apply to replace only the existing pg_backup.sh entry.
set -euo pipefail

readonly PROJECT_ROOT="${HUABANG_PROJECT_ROOT:-/srv/huabang-ai-center}"
readonly BACKUP_SCRIPT="$PROJECT_ROOT/scripts/pg_backup.sh"
readonly LOG_FILE="$PROJECT_ROOT/logs/pg_backup.log"
readonly CRON_KEY="/scripts/pg_backup.sh"

apply=false
case "${1:-}" in
  "") ;;
  --apply) apply=true ;;
  --help|-h)
    cat <<'USAGE'
Usage: install_pg_backup_cron.sh [--apply]

Without --apply, print the replacement crontab.  With --apply, replace every
existing pg_backup.sh entry with one locked daily job that writes to the
application-owned log directory.
USAGE
    exit 0
    ;;
  *)
    echo "unknown argument: ${1}" >&2
    exit 2
    ;;
esac

[[ -x "$BACKUP_SCRIPT" ]] || { echo "missing executable backup script: $BACKUP_SCRIPT" >&2; exit 2; }
mkdir -p "$(dirname "$LOG_FILE")"

existing_crontab="$(crontab -l 2>/dev/null || true)"
without_backup="$(printf '%s\n' "$existing_crontab" | awk -v key="$CRON_KEY" 'index($0, key) == 0 { print }')"
backup_entry="0 3 * * * /usr/bin/flock -n /tmp/huabang_pg_backup.lock $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
rendered_crontab="${without_backup%$'\n'}
# Huabang PostgreSQL logical backup (managed by install_pg_backup_cron.sh)
$backup_entry"

if [[ "$apply" != true ]]; then
  printf '%s\n' "$rendered_crontab"
  exit 0
fi

printf '%s\n' "$rendered_crontab" | crontab -
echo "installed daily PostgreSQL backup cron; log=$LOG_FILE"
