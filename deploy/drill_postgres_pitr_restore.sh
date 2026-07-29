#!/usr/bin/env bash
# Restore one physical base backup on an isolated loopback socket as postgres.
# It never changes the production data directory or starts on the app port.
set -euo pipefail
umask 077

readonly BACKUP_ROOT="${HUABANG_POSTGRES_BACKUP_DIR:-/var/backups/huabang-postgres}"
readonly WAL_DIR="$BACKUP_ROOT/wal"
readonly PG_BIN="/usr/lib/postgresql/16/bin"

base_dir=""
port="55432"
keep_restore=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-dir) base_dir="${2:-}"; shift 2 ;;
    --port) port="${2:-}"; shift 2 ;;
    --keep) keep_restore=true; shift ;;
    --help|-h)
      echo "Usage: drill_postgres_pitr_restore.sh --base-dir <base backup directory> [--port 55432] [--keep]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$base_dir" == "$BACKUP_ROOT"/base/base_* && -d "$base_dir" ]] || { echo "base directory must be a managed physical base backup" >&2; exit 2; }
[[ "$port" =~ ^[1-9][0-9]{3,4}$ ]] || { echo "port must be a TCP port" >&2; exit 2; }
[[ -r "$base_dir/base.tar" && -r "$base_dir/pg_wal.tar" ]] || { echo "base backup tar files are missing" >&2; exit 2; }
[[ -d "$WAL_DIR" ]] || { echo "WAL archive directory is missing" >&2; exit 2; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
restore_dir="$BACKUP_ROOT/pitr-drill-${stamp}-$$"
socket_dir="$restore_dir/socket"
started=false
cleanup() {
  local status=$?
  if [[ "$started" == true ]]; then
    "$PG_BIN/pg_ctl" -D "$restore_dir" -m fast -w stop >/dev/null 2>&1 || true
  fi
  if [[ "$keep_restore" != true && -d "$restore_dir" ]]; then
    [[ "$restore_dir" == "$BACKUP_ROOT"/pitr-drill-* ]] || exit 2
    rm -rf "$restore_dir"
  fi
  exit "$status"
}
trap cleanup EXIT

mkdir -p "$restore_dir" "$socket_dir"
tar -xf "$base_dir/base.tar" -C "$restore_dir"
tar -xf "$base_dir/pg_wal.tar" -C "$restore_dir"
touch "$restore_dir/recovery.signal"
cat > "$restore_dir/pg_hba.conf" <<'EOF'
local   all             postgres                                peer
host    all             all             127.0.0.1/32            trust
EOF
cat > "$restore_dir/postgresql.conf" <<EOF
data_directory = '$restore_dir'
hba_file = '$restore_dir/pg_hba.conf'
restore_command = '/bin/cp $WAL_DIR/%f %p'
recovery_target_action = 'promote'
port = $port
listen_addresses = '127.0.0.1'
unix_socket_directories = '$socket_dir'
EOF

start_epoch="$(date +%s)"
"$PG_BIN/pg_ctl" -D "$restore_dir" -o "-p $port -k $socket_dir" -w -t 600 start
started=true
"$PG_BIN/psql" -X -h "$socket_dir" -p "$port" -At -d huabang_ai -c "SELECT 'alembic=' || version_num FROM public.alembic_version; SELECT 'history_vouchers=' || count(*) FROM fin_history.voucher; SELECT 'history_entries=' || count(*) FROM fin_history.voucher_line; SELECT 'current_vouchers=' || count(*) FROM fin_current.voucher;"
end_epoch="$(date +%s)"
echo "pitr_restore_ready seconds=$((end_epoch-start_epoch)) restore_dir=$restore_dir"
