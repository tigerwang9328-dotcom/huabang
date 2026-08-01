#!/usr/bin/env bash
# 华邦 AI 中台一键健康检查。数据库凭据只从受限 backend/.env 生成临时 pgpass 文件。
set -o pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly ENV_FILE="${HUABANG_ENV_FILE:-$PROJECT_ROOT/backend/.env}"
readonly BACKEND_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; }

PGPASSFILE=""
trap '[[ -n "${PGPASSFILE:-}" ]] && rm -f "$PGPASSFILE"' EXIT

prepare_database_connection() {
    if [[ ! -r "$ENV_FILE" || ! -x "$BACKEND_PYTHON" ]]; then
        fail "PostgreSQL: 缺少受限环境文件或后端虚拟环境"
        return 1
    fi
    PGPASSFILE="$(mktemp)" || return 1
    chmod 600 "$PGPASSFILE"
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
PY
    IFS=$'\t' read -r DB_HOST DB_PORT DB_NAME DB_USER < <(
        "$BACKEND_PYTHON" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from dotenv import dotenv_values

values = dotenv_values(Path(sys.argv[1]))
print("\t".join((
    values.get("DB_HOST") or "localhost",
    values.get("DB_PORT") or "5432",
    values.get("DB_NAME") or "huabang_ai",
    values.get("DB_USER") or "huabang",
)))
PY
    )
}

echo "=========================================="
echo "华邦AI中台 健康检查 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 1. 后端 FastAPI
HEALTH=$(curl -s --max-time 5 http://127.0.0.1:8000/health 2>/dev/null)
if echo "$HEALTH" | grep -q 'status.*ok'; then
    ok "后端FastAPI: 运行正常"
    echo "   数据库: $(echo "$HEALTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("database","?"))')"
    echo "   Redis:  $(echo "$HEALTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("redis","?"))')"
    echo "   AI:     $(echo "$HEALTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("ai_provider","?"))')"
else
    fail "后端FastAPI: 无响应或异常"
fi

# 2. 前端（Nginx）
FRONT_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:80/ 2>/dev/null)
if [[ "$FRONT_CODE" == "200" ]]; then
    ok "前端(Nginx): HTTP $FRONT_CODE"
else
    fail "前端(Nginx): HTTP $FRONT_CODE"
fi

if prepare_database_connection; then
    export PGPASSFILE
    # 3. PostgreSQL
    PG_RESULT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" -t 2>/dev/null | tr -d ' \n')
    if [[ "$PG_RESULT" == "1" ]]; then
        TABLE_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM pg_tables WHERE schemaname IN ('sys','ods','dim','dwd','dws','dm','app','log','ai')" 2>/dev/null | tr -d ' ')
        ok "PostgreSQL: 连接正常 (表数量: $TABLE_COUNT)"
    else
        fail "PostgreSQL: 连接失败"
    fi
else
    fail "PostgreSQL: 无法加载受限数据库配置"
fi

# 4. Redis
REDIS_RESULT=$(redis-cli -h 127.0.0.1 ping 2>/dev/null)
if [[ "$REDIS_RESULT" == "PONG" ]]; then
    ok "Redis: 连接正常"
else
    fail "Redis: 连接失败"
fi

# 5. Nginx
NGINX_STATUS=$(systemctl is-active nginx 2>/dev/null)
if [[ "$NGINX_STATUS" == "active" ]]; then
    ok "Nginx: 运行中"
else
    fail "Nginx: $NGINX_STATUS"
fi

# 6. systemd 后端服务
BACKEND_STATUS=$(systemctl is-active huabang-backend 2>/dev/null)
if [[ "$BACKEND_STATUS" == "active" ]]; then
    ok "systemd服务: 运行中"
else
    fail "systemd服务: $BACKEND_STATUS"
fi

if [[ -n "${DB_HOST:-}" ]]; then
    # 7. 最近数据同步
    LAST_SYNC=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT to_char(max(created_at),'YYYY-MM-DD HH24:MI') FROM log.log_data_sync WHERE status='success'" 2>/dev/null | tr -d ' ')
    if [[ -n "$LAST_SYNC" && "$LAST_SYNC" != "null" ]]; then
        ok "最近成功同步: $LAST_SYNC"
    else
        warn "最近成功同步: 无记录（可能尚未导入数据）"
    fi

    # 8. 最近 ETL
    LAST_ETL=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT to_char(max(started_at),'YYYY-MM-DD HH24:MI') FROM log.log_etl_run WHERE status='success'" 2>/dev/null | tr -d ' ')
    if [[ -n "$LAST_ETL" && "$LAST_ETL" != "null" ]]; then
        ok "最近成功ETL: $LAST_ETL"
    else
        warn "最近成功ETL: 无记录（可能尚未执行ETL）"
    fi

    # 9. 最近钉钉推送
    LAST_PUSH=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT to_char(max(created_at),'YYYY-MM-DD HH24:MI') FROM log.log_dingtalk_push WHERE is_success=true" 2>/dev/null | tr -d ' ')
    if [[ -n "$LAST_PUSH" && "$LAST_PUSH" != "null" ]]; then
        ok "最近成功推送: $LAST_PUSH"
    else
        warn "最近成功推送: 无记录"
    fi
fi

# 10. 备份检查
LATEST_BACKUP=$(ls -t /srv/backups/pg/*.sql.gz 2>/dev/null | head -1)
if [[ -n "$LATEST_BACKUP" ]]; then
    BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 3600 ))
    if [[ "$BACKUP_AGE" -lt 25 ]]; then
        ok "最近备份: $(basename "$LATEST_BACKUP") (${BACKUP_AGE}小时前)"
    else
        warn "最近备份: $(basename "$LATEST_BACKUP") (${BACKUP_AGE}小时前，超过24小时！)"
    fi
else
    warn "备份: 尚无备份文件"
fi

echo "=========================================="
