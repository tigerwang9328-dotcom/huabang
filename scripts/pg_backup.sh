#!/usr/bin/env bash
# PostgreSQL daily backup.  Credentials are loaded only into a temporary pgpass
# file created from the restricted backend/.env configuration.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly ENV_FILE="${HUABANG_ENV_FILE:-$PROJECT_ROOT/backend/.env}"
readonly BACKEND_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
readonly BACKUP_DIR="${HUABANG_PG_BACKUP_DIR:-/srv/backups/pg}"
readonly KEEP_DAYS="${HUABANG_PG_BACKUP_KEEP_DAYS:-7}"

[[ -r "$ENV_FILE" ]] || { echo "missing environment file: $ENV_FILE" >&2; exit 2; }
[[ -x "$BACKEND_PYTHON" ]] || { echo "missing backend virtualenv Python: $BACKEND_PYTHON" >&2; exit 2; }
[[ "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "backup retention must be a positive day count" >&2; exit 2; }

mkdir -p "$BACKUP_DIR"
PGPASSFILE="$(mktemp "$BACKUP_DIR/.pgpass.XXXXXX")"
BACKUP_TMP=""
trap 'rm -f "${PGPASSFILE:-}" "${BACKUP_TMP:-}"' EXIT
chmod 600 "$PGPASSFILE"

IFS=$'\t' read -r DB_HOST DB_PORT DB_NAME DB_USER < <(
  "$BACKEND_PYTHON" - "$ENV_FILE" "$PGPASSFILE" <<'PY'
from pathlib import Path
import sys

from dotenv import dotenv_values

env_path, pgpass_path = map(Path, sys.argv[1:])
values = dotenv_values(env_path)
host = values.get("DB_HOST") or "localhost"
port = values.get("DB_PORT") or "5432"
database = values.get("DB_NAME") or "huabang_ai"
user = values.get("DB_USER") or "huabang"
password = values.get("DB_PASSWORD")
if not password:
    raise SystemExit("DB_PASSWORD is missing")
Path(pgpass_path).write_text(f"{host}:{port}:{database}:{user}:{password}\n", encoding="utf-8")
Path(pgpass_path).chmod(0o600)
print("\t".join((host, port, database, user)))
PY
)
export PGPASSFILE

DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"
BACKUP_TMP="${BACKUP_FILE}.tmp"

echo "[$(date)] 开始备份 $DB_NAME..."
if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_TMP"; then
    mv "$BACKUP_TMP" "$BACKUP_FILE"
    BACKUP_TMP=""
    SIZE="$(du -sh "$BACKUP_FILE" | cut -f1)"
    echo "[$(date)] 备份成功: $BACKUP_FILE ($SIZE)"
    find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +"$KEEP_DAYS" -print -delete
    echo "[$(date)] 已清理 ${KEEP_DAYS} 天前的旧备份"
else
    echo "[$(date)] 备份失败！" >&2
    exit 1
fi
