#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "Run as a deployment operator; the script uses sudo only for the PostgreSQL OS account." >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
backend_root="$repo_root/backend"
database_name="${HUABANG_DOUYIN_DATABASE_NAME:-huabang_ai}"
if [[ ! "$database_name" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "HUABANG_DOUYIN_DATABASE_NAME must be an identifier." >&2
  exit 2
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$database_name" -f "$repo_root/deploy/bootstrap_douyin_color_migrator.sql"
# The PostgreSQL OS account authenticates through the local socket. The dummy
# application settings only allow model import; Alembic uses the explicit URL.
export ALEMBIC_DATABASE_URL="postgresql+psycopg2://postgres@/$database_name?host=/var/run/postgresql"
exec sudo -u postgres env \
  APP_SECRET_KEY=alembic-migration-only \
  DB_PASSWORD=alembic-migration-only \
  JWT_SECRET_KEY=alembic-migration-only \
  ALEMBIC_DATABASE_URL="$ALEMBIC_DATABASE_URL" \
  "$backend_root/.venv/bin/python" -m alembic -c "$backend_root/alembic.ini" upgrade head
