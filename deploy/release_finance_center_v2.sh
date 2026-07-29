#!/usr/bin/env bash
# Finance V2 production entrypoint.  It is intentionally initial-read-only:
# it publishes immutable Kingdee history, leaves all V2 write gates closed,
# and never closes or redirects legacy finance write paths.
set -euo pipefail
umask 077

readonly PROJECT_ROOT="/srv/huabang-ai-center"
readonly BACKEND_DIR="$PROJECT_ROOT/backend"
readonly FRONTEND_DIR="$PROJECT_ROOT/frontend"
readonly ENV_FILE="$BACKEND_DIR/.env"
readonly VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
readonly DATABASE_NAME="huabang_ai"
readonly BACKUP_DIR="/var/backups/huabang-finance-v2"
readonly LOG_DIR="$PROJECT_ROOT/.finance-v2-release-logs"
readonly OFFICIAL_ACCOUNT_SETS=(AIS20251127140257 AIS20260305112309 AIS20260305112733)

execute=false
release_ref=""
expected_commit=""
history_manifest=""
history_manifest_sha256=""
expected_history_vouchers=""
expected_history_entries=""
previous_commit=""
previous_ref=""
previous_env_backup=""
previous_dist=""
next_dist=""
credentials_file=""
release_succeeded=false
runtime_activated=false

usage() {
  cat <<'USAGE'
Usage:
  release_finance_center_v2.sh \
    --release-ref <remote-branch-or-tag> \
    --expected-commit <40-hex-commit> \
    --history-manifest </absolute/manifest.json> \
    --history-manifest-sha256 <64-hex-sha256> \
    --expected-history-vouchers <positive-int> \
    --expected-history-entries <positive-int> \
    [--execute]

Without --execute this command performs no production mutation and prints the
required immutable inputs.  The production mutation is an initial read-only
release: all Finance V2 draft/review/post gates remain closed.
USAGE
}

die() {
  echo "Finance V2 release blocked: $*" >&2
  exit 2
}

is_safe_ref() { [[ "$1" =~ ^[A-Za-z0-9._/-]+$ ]] && [[ "$1" != -* ]]; }
is_hex40() { [[ "$1" =~ ^[0-9a-fA-F]{40}$ ]]; }
is_hex64() { [[ "$1" =~ ^[0-9a-fA-F]{64}$ ]]; }
is_positive_integer() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-ref) release_ref="${2:-}"; shift 2 ;;
    --expected-commit) expected_commit="${2:-}"; shift 2 ;;
    --history-manifest) history_manifest="${2:-}"; shift 2 ;;
    --history-manifest-sha256) history_manifest_sha256="${2:-}"; shift 2 ;;
    --expected-history-vouchers) expected_history_vouchers="${2:-}"; shift 2 ;;
    --expected-history-entries) expected_history_entries="${2:-}"; shift 2 ;;
    --execute) execute=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

is_safe_ref "$release_ref" || die "--release-ref must be a safe remote ref"
is_hex40 "$expected_commit" || die "--expected-commit must be a 40-hex commit"
[[ "$history_manifest" = /* && -f "$history_manifest" ]] || die "--history-manifest must be an existing absolute file"
is_hex64 "$history_manifest_sha256" || die "--history-manifest-sha256 must be a 64-hex digest"
is_positive_integer "$expected_history_vouchers" || die "--expected-history-vouchers must be positive"
is_positive_integer "$expected_history_entries" || die "--expected-history-entries must be positive"
[[ -x "$VENV_PYTHON" ]] || die "backend virtualenv Python is unavailable"
[[ -f "$ENV_FILE" ]] || die "backend environment file is unavailable"

actual_manifest_sha256="$(sha256sum "$history_manifest" | awk '{print $1}')"
[[ "${actual_manifest_sha256,,}" == "${history_manifest_sha256,,}" ]] || die "history manifest digest does not match the approved input"

if [[ "$execute" != true ]]; then
  echo "Finance V2 release is a dry preflight. Re-run with --execute after recording this immutable input set:"
  printf 'release_ref=%s\nexpected_commit=%s\nhistory_manifest=%s\nexpected_history_vouchers=%s\nexpected_history_entries=%s\n' \
    "$release_ref" "$expected_commit" "$history_manifest" "$expected_history_vouchers" "$expected_history_entries"
  exit 0
fi

[[ "$EUID" -ne 0 ]] || die "run as the application owner; the script uses narrowly scoped sudo commands"
sudo -v

mkdir -p "$LOG_DIR"
release_log="$LOG_DIR/release-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$release_log") 2>&1

exec 9>"$PROJECT_ROOT/.finance-v2-release.lock"
flock -n 9 || die "another Finance V2 release holds the deployment lock"

postgres_sql() {
  local sql="$1"
  local local_file remote_file status=0
  local_file="$(mktemp "$PROJECT_ROOT/.finance-v2-sql.XXXXXX")"
  remote_file="${local_file}.postgres"
  printf '%s\n' "$sql" > "$local_file"
  chmod 600 "$local_file"
  if ! sudo -n install -o postgres -g postgres -m 600 "$local_file" "$remote_file"; then
    rm -f "$local_file"
    return 1
  fi
  rm -f "$local_file"
  sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" -f "$remote_file" || status=$?
  sudo -n rm -f "$remote_file" || return 1
  return "$status"
}

clear_temporary_role_passwords() {
  postgres_sql "ALTER ROLE fin_migrator PASSWORD NULL; ALTER ROLE fin_history_importer PASSWORD NULL;"
}

clear_fin_app_password_after_failed_release() {
  postgres_sql "ALTER ROLE fin_app PASSWORD NULL;"
}

restore_env_file() {
  if [[ -n "$previous_env_backup" && -f "$previous_env_backup" ]]; then
    cp -p "$previous_env_backup" "$ENV_FILE"
  fi
}

rollback_runtime() {
  local failure_status="$1"
  if [[ "$release_succeeded" == true ]]; then
    return
  fi
  echo "Finance V2 release failed; restoring only code/config/frontend runtime. Finance schema/history data is retained for audit."
  set +e
  if [[ -n "$previous_commit" ]]; then
    if [[ -n "$previous_ref" ]]; then
      git -C "$PROJECT_ROOT" checkout "$previous_ref"
      git -C "$PROJECT_ROOT" reset --hard "$previous_commit"
    else
      git -C "$PROJECT_ROOT" checkout --detach "$previous_commit"
    fi
  fi
  restore_env_file
  if [[ -n "$previous_dist" && -d "$previous_dist" ]]; then
    if [[ -d "$FRONTEND_DIR/dist" ]]; then
      mv "$FRONTEND_DIR/dist" "${FRONTEND_DIR}/.finance-v2-failed-dist-$(date -u +%s)"
    fi
    mv "$previous_dist" "$FRONTEND_DIR/dist"
  fi
  if [[ "$runtime_activated" == true ]]; then
    sudo -n systemctl restart huabang-backend.service
  fi
  if [[ -n "$credentials_file" && -f "$credentials_file" ]]; then
    rm -f "$credentials_file"
  fi
  clear_temporary_role_passwords
  clear_fin_app_password_after_failed_release
  trap - EXIT
  exit "$failure_status"
}

cleanup() {
  local status=$?
  if [[ "$status" -ne 0 ]]; then
    rollback_runtime "$status"
  fi
  if [[ -n "$credentials_file" && -f "$credentials_file" ]]; then
    rm -f "$credentials_file"
  fi
  if [[ "$release_succeeded" == true && -n "$previous_env_backup" && -f "$previous_env_backup" ]]; then
    rm -f "$previous_env_backup"
  fi
  clear_temporary_role_passwords
}
trap cleanup EXIT

git -C "$PROJECT_ROOT" diff --quiet || die "production worktree has unstaged tracked changes"
git -C "$PROJECT_ROOT" diff --cached --quiet || die "production worktree has staged changes"
previous_commit="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
previous_ref="$(git -C "$PROJECT_ROOT" symbolic-ref --short -q HEAD || true)"

if resolved_commit="$(git -C "$PROJECT_ROOT" rev-parse --verify "${release_ref}^{commit}" 2>/dev/null)"; then
  [[ "${resolved_commit,,}" == "${expected_commit,,}" ]] || die "local release ref does not match --expected-commit"
else
  GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes" \
    git -C "$PROJECT_ROOT" fetch --tags origin "$release_ref"
  resolved_commit="$(git -C "$PROJECT_ROOT" rev-parse --verify FETCH_HEAD)"
  [[ "${resolved_commit,,}" == "${expected_commit,,}" ]] || die "fetched release ref does not match --expected-commit"
fi
git -C "$PROJECT_ROOT" checkout --detach "$expected_commit"

"$VENV_PYTHON" -m pip install --no-input --disable-pip-version-check -r "$BACKEND_DIR/requirements.txt"
"$VENV_PYTHON" -m pip check

backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$BACKUP_DIR/huabang_ai_finance_v2_release_${backup_stamp}.dump"
backup_tmp="${backup_file}.tmp"
sudo -n install -d -o postgres -g postgres -m 700 "$BACKUP_DIR"
sudo -n -u postgres bash -c "umask 077; pg_dump -Fc -d '$DATABASE_NAME' > '$backup_tmp'; mv '$backup_tmp' '$backup_file'"
sudo -n -u postgres sha256sum "$backup_file"

sudo -n -u postgres psql -X -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" -f "$BACKEND_DIR/scripts/bootstrap_finance_database_roles.sql"
postgres_sql "GRANT CONNECT ON DATABASE $DATABASE_NAME TO fin_migrator, fin_app, fin_history_importer, fin_readonly_auditor;"

credentials_file="$(mktemp "$PROJECT_ROOT/.finance-v2-credentials.XXXXXX")"
chmod 600 "$credentials_file"
printf 'fin_migrator=%s\nfin_app=%s\nfin_history_importer=%s\n' \
  "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$credentials_file"

read_credential() {
  local name="$1"
  awk -F= -v wanted="$name" '$1 == wanted {print $2; exit}' "$credentials_file"
}

postgres_sql "ALTER ROLE fin_migrator PASSWORD '$(read_credential fin_migrator)';"
postgres_sql "ALTER ROLE fin_app PASSWORD '$(read_credential fin_app)';"
postgres_sql "ALTER ROLE fin_history_importer PASSWORD '$(read_credential fin_history_importer)';"

run_backend_with_env() {
  local mode="$1"
  shift
  "$VENV_PYTHON" - "$mode" "$ENV_FILE" "$credentials_file" "$BACKEND_DIR" "$@" <<'PY'
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

mode, env_file, credential_file, backend_dir, *command = sys.argv[1:]
values = dotenv_values(env_file)
for key, value in values.items():
    if value is not None:
        os.environ[key] = value
credentials = dict(
    line.split("=", 1)
    for line in Path(credential_file).read_text(encoding="utf-8").splitlines()
    if "=" in line
)
if mode == "migrate":
    os.environ["DB_USER"] = "fin_migrator"
    os.environ["DB_PASSWORD"] = credentials["fin_migrator"]
    os.environ["PGOPTIONS"] = "-c role=fin_schema_owner"
elif mode == "history_import":
    os.environ["DB_USER"] = "fin_history_importer"
    os.environ["DB_PASSWORD"] = credentials["fin_history_importer"]
elif mode != "shared":
    raise SystemExit(f"unsupported backend execution mode: {mode}")
os.chdir(backend_dir)
os.execv(sys.executable, [sys.executable, *command])
PY
}

run_backend_with_env migrate -m alembic -c alembic.ini upgrade head
run_backend_with_env shared scripts/verify_finance_database_roles.py
run_backend_with_env shared scripts/seed_finance_v2_permissions.py

history_import_args=(scripts/import_finance_v2_history.py "$history_manifest" --execute --publish)
for account_set in "${OFFICIAL_ACCOUNT_SETS[@]}"; do
  history_import_args+=(--account-set "$account_set")
done
run_backend_with_env history_import "${history_import_args[@]}"

clear_temporary_role_passwords

previous_env_backup="$ENV_FILE.finance-v2-pre-release-$backup_stamp"
cp -p "$ENV_FILE" "$previous_env_backup"
"$VENV_PYTHON" - "$ENV_FILE" "$credentials_file" <<'PY'
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

env_path = Path(sys.argv[1])
credentials = dict(
    line.split("=", 1)
    for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
    if "=" in line
)
values = dotenv_values(env_path)
required = ("DB_HOST", "DB_PORT", "DB_NAME")
missing = [key for key in required if not values.get(key)]
if missing:
    raise SystemExit("existing environment is missing database coordinates: " + ", ".join(missing))
updates = {
    "FINANCE_DB_HOST": values["DB_HOST"],
    "FINANCE_DB_PORT": values["DB_PORT"],
    "FINANCE_DB_NAME": values["DB_NAME"],
    "FINANCE_DB_USER": "fin_app",
    "FINANCE_DB_PASSWORD": credentials["fin_app"],
}
content = env_path.read_text(encoding="utf-8")
for key, value in updates.items():
    replacement = f"{key}={value}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    content, substitutions = pattern.subn(replacement, content, count=1)
    if substitutions == 0:
        content += "\n" + replacement + "\n"
temporary = env_path.with_name(env_path.name + ".finance-v2-next")
temporary.write_text(content, encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, env_path)
PY

cd "$FRONTEND_DIR"
npm ci --no-audit --no-fund
npm run type-check
next_dist="$(mktemp -d "$FRONTEND_DIR/.finance-v2-dist.XXXXXX")"
npm run build -- --outDir "$next_dist"

sudo -n systemctl restart huabang-backend.service
runtime_activated=true
for attempt in $(seq 1 20); do
  if curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  [[ "$attempt" -lt 20 ]] || die "backend health endpoint did not recover after restart"
  sleep 1
done

run_backend_with_env shared "$PROJECT_ROOT/deploy/verify_finance_center_v2.py" \
  --expected-history-vouchers "$expected_history_vouchers" \
  --expected-history-entries "$expected_history_entries" \
  --expected-current-vouchers 0

previous_dist="$FRONTEND_DIR/.finance-v2-previous-dist-$backup_stamp"
mv "$FRONTEND_DIR/dist" "$previous_dist"
mv "$next_dist" "$FRONTEND_DIR/dist"
next_dist=""

release_succeeded=true
echo "Finance V2 read-only release completed. Log: $release_log"
echo "Legacy finance write paths were not changed; Finance V2 draft_enabled, review_enabled and post_enabled remain closed."
