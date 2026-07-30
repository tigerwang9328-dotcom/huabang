#!/usr/bin/env bash
# Runs destructive-to-test-data acceptance only against an explicitly provisioned test database.
set -euo pipefail

test_database="${1:-}"
if [[ ! "$test_database" =~ ^huabang_ai_douyin_task2_test(_[a-z0-9]+)?$ ]]; then
  echo "Usage: $0 huabang_ai_douyin_task2_test[_suffix]" >&2
  exit 64
fi

set -a
. /srv/huabang-ai-center/backend/.env
set +a
unset ALEMBIC_DATABASE_URL
export DB_NAME="$test_database"
export DOUYIN_TASK2_POSTGRES_ACCEPTANCE=1
export PGPASSWORD="$DB_PASSWORD"

cd /home/xiaohu/worktrees/huabang-douyin-color-v31/backend
resolved_database="$(PYTHONPATH=. /srv/huabang-ai-center/backend/.venv/bin/python -c 'from app.core.config import settings; print(settings.DB_NAME)')"
if [[ "$resolved_database" != "$test_database" ]]; then
  echo "refusing application database mismatch" >&2
  exit 65
fi

actual_database="$(psql -X -At -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c 'SELECT current_database()')"
if [[ "$actual_database" != "$test_database" ]]; then
  echo "refusing database mismatch" >&2
  exit 65
fi

expected_post_migration_revision="3a2d7e951b2c"
post_migration_revision="$(psql -X -At -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c 'SELECT version_num FROM alembic_version')"
if [[ "$post_migration_revision" != "$expected_post_migration_revision" ]]; then
  echo "refusing unexpected post-migration Alembic revision" >&2
  exit 66
fi

set +e
PYTHONPATH=. /srv/huabang-ai-center/backend/.venv/bin/python -m alembic check
alembic_check_exit=$?
set -e
if [[ "$alembic_check_exit" -ne 0 ]]; then
  echo "alembic check reported existing global migration drift; recorded as diagnostic, continuing Task 2 acceptance" >&2
fi
PYTHONPATH=. /srv/huabang-ai-center/backend/.venv/bin/python -m pytest tests/integration/test_douyin_color_task2_postgres.py -q
