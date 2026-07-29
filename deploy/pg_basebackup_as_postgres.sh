#!/usr/bin/env bash
# Runs only from the root-owned systemd service as the PostgreSQL OS account.
set -euo pipefail
umask 077

readonly BACKUP_ROOT="${HUABANG_POSTGRES_BACKUP_DIR:-/var/backups/huabang-postgres}"
readonly BASE_DIR="$BACKUP_ROOT/base"
readonly WAL_DIR="$BACKUP_ROOT/wal"
readonly BASE_KEEP_DAYS="${HUABANG_POSTGRES_BASE_KEEP_DAYS:-14}"
readonly WAL_KEEP_DAYS="${HUABANG_POSTGRES_WAL_KEEP_DAYS:-16}"

[[ "$BASE_KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "base backup retention must be positive" >&2; exit 2; }
[[ "$WAL_KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "WAL retention must be positive" >&2; exit 2; }
mkdir -p "$BASE_DIR" "$WAL_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BASE_DIR/base_$stamp"
temporary="$(mktemp -d "$BASE_DIR/.base_${stamp}.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT

/usr/bin/pg_basebackup --format=tar --wal-method=stream --checkpoint=fast --label="huabang-$stamp" --pgdata="$temporary"
(cd "$temporary" && /usr/bin/sha256sum ./* > SHA256SUMS)
mv "$temporary" "$target"
temporary=""

find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -name 'base_*' -mtime +"$BASE_KEEP_DAYS" -exec rm -rf {} +
find "$WAL_DIR" -mindepth 1 -maxdepth 1 -type f -mtime +"$WAL_KEEP_DAYS" -delete
echo "basebackup_ready directory=$target"
