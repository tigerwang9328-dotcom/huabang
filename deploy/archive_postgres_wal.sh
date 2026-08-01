#!/usr/bin/env bash
# Called by PostgreSQL's archive_command as the postgres OS account.
set -euo pipefail
umask 077

readonly ARCHIVE_DIR="${HUABANG_POSTGRES_WAL_ARCHIVE_DIR:-/var/backups/huabang-postgres/wal}"
archive_source="${1:?archive source path is required}"
archive_name="${2:?archive file name is required}"

[[ "$archive_name" != */* ]] || { echo "archive file name must not include a path" >&2; exit 2; }
[[ -f "$archive_source" ]] || { echo "archive source does not exist: $archive_source" >&2; exit 2; }
mkdir -p "$ARCHIVE_DIR"

archive_target="$ARCHIVE_DIR/$archive_name"
archive_tmp="${archive_target}.tmp.$$"
if [[ -f "$archive_target" ]]; then
  exit 0
fi
cp "$archive_source" "$archive_tmp"
mv "$archive_tmp" "$archive_target"
