#!/usr/bin/env bash
# Rehearse the post-1fdf Finance V2 migrations on an explicitly named recovery
# database.  This script never targets the production `huabang_ai` database,
# never restarts the service, and leaves the recovery database at the current
# Alembic head after proving a down/up round trip.
set -euo pipefail
umask 077

readonly PROJECT_ROOT="/srv/huabang-ai-center"
readonly BACKEND_DIR="$PROJECT_ROOT/backend"
readonly ENV_FILE="$BACKEND_DIR/.env"
readonly VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
readonly BASELINE_REVISION="1fdf4577d7d8"

database_name=""
execute=false
credentials_file=""
temporary_password=""

usage() {
  cat <<'USAGE'
Usage:
  rehearse_finance_v2_migrations.sh \
    --database-name <huabang_ai_finance_drill_...> \
    [--execute]

Without --execute, this performs only argument validation.  With --execute it
uses an interactive sudo authorization once, migrates an existing recovery
database from 1fdf4577d7d8 to head, downgrades it to 1fdf4577d7d8, upgrades it
again, and runs the read-only Finance role verifier.  The production database
name is rejected by construction.
USAGE
}

die() {
  echo "Finance V2 recovery rehearsal blocked: $*" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database-name) database_name="${2:-}"; shift 2 ;;
    --execute) execute=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "$database_name" =~ ^huabang_ai_finance_drill_[a-z0-9_]+$ ]] || \
  die "--database-name must be a dedicated huabang_ai_finance_drill_ recovery database"
[[ -x "$VENV_PYTHON" ]] || die "backend virtualenv Python is unavailable"
[[ -f "$ENV_FILE" ]] || die "backend environment file is unavailable"

if [[ "$execute" != true ]]; then
  echo "Recovery rehearsal is a dry preflight. Re-run with --execute only for: $database_name"
  exit 0
fi

[[ "$EUID" -ne 0 ]] || die "run as the application owner; sudo records the responsible operator"
command -v openssl >/dev/null || die "openssl is required for an in-memory temporary migration credential"

exec 9>"$PROJECT_ROOT/.finance-v2-rehearsal.lock"
flock -n 9 || die "another Finance V2 recovery rehearsal already holds the lock"

# This deliberately prompts only through the operator's terminal.  Every
# privileged operation after this point is non-interactive and fails closed if
# the authorization expires.
sudo -v

sudo_run() {
  command sudo -n "$@"
}

postgres_cluster_sql() {
  printf '%s\n' "$1" | sudo_run -u postgres psql -X -v ON_ERROR_STOP=1 -d postgres
}

postgres_target_sql() {
  printf '%s\n' "$1" | sudo_run -u postgres psql -X -v ON_ERROR_STOP=1 -d "$database_name"
}

clear_temporary_password() {
  if [[ -n "$temporary_password" ]]; then
    postgres_cluster_sql "ALTER ROLE fin_migrator PASSWORD NULL;" >/dev/null || \
      echo "WARNING: temporary fin_migrator password could not be cleared automatically" >&2
    temporary_password=""
  fi
}

cleanup() {
  local status=$?
  clear_temporary_password
  if [[ -n "$credentials_file" && -f "$credentials_file" ]]; then
    rm -f "$credentials_file"
  fi
  exit "$status"
}
trap cleanup EXIT

current_revision="$(sudo_run -u postgres psql -X -At -v ON_ERROR_STOP=1 -d "$database_name" \
  -c "SELECT version_num FROM public.alembic_version")"
[[ "$current_revision" == "$BASELINE_REVISION" ]] || \
  die "recovery database must be at baseline $BASELINE_REVISION, found ${current_revision:-<none>}"

# Re-apply the checked-in least-privilege baseline before creating objects that
# the new migrations add.  This changes only the explicitly named recovery DB.
postgres_target_sql "$(<"$BACKEND_DIR/scripts/bootstrap_finance_database_roles.sql")"

temporary_password="$(openssl rand -hex 32)"
postgres_cluster_sql "ALTER ROLE fin_migrator PASSWORD '$temporary_password';"
credentials_file="$(mktemp "$PROJECT_ROOT/.finance-v2-rehearsal-credentials.XXXXXX")"
printf 'fin_migrator=%s\n' "$temporary_password" > "$credentials_file"
chmod 600 "$credentials_file"

run_migrator() {
  "$VENV_PYTHON" - "$ENV_FILE" "$credentials_file" "$BACKEND_DIR" "$database_name" "$@" <<'PY'
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

env_file, credential_file, backend_dir, database_name, *command = sys.argv[1:]
for key, value in dotenv_values(env_file).items():
    if value is not None:
        os.environ[key] = value
credential = Path(credential_file).read_text(encoding="utf-8").strip().split("=", 1)[1]
os.environ.update(
    DB_NAME=database_name,
    DB_USER="fin_migrator",
    DB_PASSWORD=credential,
    PGOPTIONS="-c role=fin_schema_owner",
    PYTHONPATH=backend_dir + os.pathsep + os.environ.get("PYTHONPATH", ""),
)
os.chdir(backend_dir)
os.execv(sys.executable, [sys.executable, *command])
PY
}

run_migrator -m alembic -c alembic.ini upgrade head
run_migrator scripts/verify_finance_database_roles.py
run_migrator -m alembic -c alembic.ini downgrade "$BASELINE_REVISION"

current_revision="$(sudo_run -u postgres psql -X -At -v ON_ERROR_STOP=1 -d "$database_name" \
  -c "SELECT version_num FROM public.alembic_version")"
[[ "$current_revision" == "$BASELINE_REVISION" ]] || die "downgrade did not return to $BASELINE_REVISION"

run_migrator -m alembic -c alembic.ini upgrade head
run_migrator scripts/verify_finance_database_roles.py

echo "Finance V2 recovery migration rehearsal completed: database=$database_name baseline=$BASELINE_REVISION"
