#!/usr/bin/env bash
# Runs only from the root-owned systemd service as the PostgreSQL OS account.
# It intentionally does not consume the application database credential.
set -euo pipefail
umask 077

readonly DATABASE_NAME="${HUABANG_BACKUP_DATABASE:-huabang_ai}"
readonly BACKUP_DIR="${HUABANG_POSTGRES_BACKUP_DIR:-/var/backups/huabang-postgres}"
readonly KEEP_DAYS="${HUABANG_POSTGRES_BACKUP_KEEP_DAYS:-14}"

[[ "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "backup retention must be a positive day count" >&2; exit 2; }
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$BACKUP_DIR/${DATABASE_NAME}_${stamp}.dump"
backup_tmp="${backup_file}.tmp"
checksum_tmp="${backup_file}.sha256.tmp"
trap 'rm -f "$backup_tmp" "$checksum_tmp"' EXIT

/usr/bin/pg_dump -Fc --no-owner --no-privileges -d "$DATABASE_NAME" -f "$backup_tmp"
mv "$backup_tmp" "$backup_file"
/usr/bin/sha256sum "$backup_file" > "$checksum_tmp"
mv "$checksum_tmp" "${backup_file}.sha256"

find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "${DATABASE_NAME}_*.dump" -o -name "${DATABASE_NAME}_*.dump.sha256" \) -mtime +"$KEEP_DAYS" -delete
echo "backup_ready file=$backup_file"
