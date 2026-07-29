#!/usr/bin/env bash
# Install the WAL archiver and physical base-backup timer. The caller must
# explicitly request the PostgreSQL restart required by archive_mode.
set -euo pipefail

readonly PROJECT_ROOT="${HUABANG_PROJECT_ROOT:-/srv/huabang-ai-center}"
readonly TARGET_DIR="/usr/local/lib/huabang"
readonly CONF_DIR="/etc/postgresql/16/main/conf.d"
readonly CLUSTER_SERVICE="postgresql@16-main.service"

apply=false
restart_postgresql=false
for argument in "$@"; do
  case "$argument" in
    --apply) apply=true ;;
    --restart-postgresql) restart_postgresql=true ;;
    --help|-h)
      echo "Usage: install_postgres_pitr.sh --apply [--restart-postgresql]"
      exit 0
      ;;
    *) echo "unknown argument: $argument" >&2; exit 2 ;;
  esac
done

[[ "$EUID" -eq 0 ]] || { echo "run as root via sudo" >&2; exit 2; }
for required in \
  "$PROJECT_ROOT/deploy/archive_postgres_wal.sh" \
  "$PROJECT_ROOT/deploy/pg_basebackup_as_postgres.sh" \
  "$PROJECT_ROOT/deploy/postgresql/huabang-finance-pitr.conf" \
  "$PROJECT_ROOT/deploy/systemd/huabang-postgres-basebackup.service" \
  "$PROJECT_ROOT/deploy/systemd/huabang-postgres-basebackup.timer"; do
  [[ -f "$required" ]] || { echo "missing release asset: $required" >&2; exit 2; }
done

if [[ "$apply" != true ]]; then
  cat <<EOF
Would install root-owned WAL/archive runners and PostgreSQL configuration.
Would enable huabang-postgres-basebackup.timer.
Would restart $CLUSTER_SERVICE only when --restart-postgresql is also given.
EOF
  exit 0
fi

install -d -o root -g root -m 755 "$TARGET_DIR"
install -d -o postgres -g postgres -m 700 /var/backups/huabang-postgres /var/backups/huabang-postgres/base /var/backups/huabang-postgres/wal
install -o root -g root -m 755 "$PROJECT_ROOT/deploy/archive_postgres_wal.sh" "$TARGET_DIR/archive_postgres_wal.sh"
install -o root -g root -m 755 "$PROJECT_ROOT/deploy/pg_basebackup_as_postgres.sh" "$TARGET_DIR/pg_basebackup_as_postgres.sh"
install -o root -g root -m 644 "$PROJECT_ROOT/deploy/postgresql/huabang-finance-pitr.conf" "$CONF_DIR/huabang-finance-pitr.conf"
install -o root -g root -m 644 "$PROJECT_ROOT/deploy/systemd/huabang-postgres-basebackup.service" /etc/systemd/system/huabang-postgres-basebackup.service
install -o root -g root -m 644 "$PROJECT_ROOT/deploy/systemd/huabang-postgres-basebackup.timer" /etc/systemd/system/huabang-postgres-basebackup.timer

systemctl daemon-reload
systemctl enable --now huabang-postgres-basebackup.timer
if [[ "$restart_postgresql" == true ]]; then
  systemctl restart "$CLUSTER_SERVICE"
fi
echo "installed PostgreSQL PITR assets; restart_postgresql=$restart_postgresql"
