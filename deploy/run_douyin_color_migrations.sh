#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "Run as a deployment operator; the script uses sudo only for the PostgreSQL OS account." >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
backend_root="$repo_root/backend"
migration_python="${HUABANG_DOUYIN_PYTHON_BIN:-$backend_root/.venv/bin/python}"
if [[ ! -x "$migration_python" ]]; then
  echo "HUABANG_DOUYIN_PYTHON_BIN must point to an executable Python runtime." >&2
  exit 3
fi

if [[ -z "${HUABANG_DOUYIN_DATABASE_NAME:-}" ]]; then
  echo "HUABANG_DOUYIN_DATABASE_NAME must be set explicitly." >&2
  exit 2
fi
database_name="$HUABANG_DOUYIN_DATABASE_NAME"
if [[ ! "$database_name" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "HUABANG_DOUYIN_DATABASE_NAME must be an identifier." >&2
  exit 2
fi
if [[ "$database_name" == "huabang_ai" && "${HUABANG_DOUYIN_CONFIRM_PRODUCTION:-}" != "MIGRATE_HUABANG_AI" ]]; then
  echo "Set HUABANG_DOUYIN_CONFIRM_PRODUCTION=MIGRATE_HUABANG_AI for the production database." >&2
  exit 4
fi
expected_pre_migration_revision="e951b2d0a6c4"
pre_migration_revision="$(sudo -u postgres psql -X -At -v ON_ERROR_STOP=1 -d "$database_name" -c 'SELECT version_num FROM alembic_version')"
if [[ "$pre_migration_revision" != "$expected_pre_migration_revision" ]]; then
  echo "refusing unexpected pre-migration Alembic revision" >&2
  exit 5
fi
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$database_name" -f "$repo_root/deploy/bootstrap_douyin_color_migrator.sql"
# The PostgreSQL OS account authenticates through the local socket. The dummy
# application settings only allow model import; Alembic uses the explicit URL.
export ALEMBIC_DATABASE_URL="postgresql+psycopg2://postgres@/$database_name"
exec sudo -u postgres env \
  APP_SECRET_KEY=alembic-migration-only \
  DB_PASSWORD=alembic-migration-only \
  JWT_SECRET_KEY=alembic-migration-only \
  ALEMBIC_DATABASE_URL="$ALEMBIC_DATABASE_URL" \
  "$migration_python" -m alembic -c "$backend_root/alembic.ini" upgrade head
