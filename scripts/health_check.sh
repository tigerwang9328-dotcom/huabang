#!/bin/bash
# 华邦AI中台 一键健康检查脚本
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; }

echo "=========================================="
echo "华邦AI中台 健康检查 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 1. 后端FastAPI
HEALTH=$(curl -s --max-time 5 http://127.0.0.1:8000/health 2>/dev/null)
if echo "$HEALTH" | grep -q 'status.*ok'; then
    ok "后端FastAPI: 运行正常"
    echo "   数据库: $(echo $HEALTH | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("database","?"))')"
    echo "   Redis:  $(echo $HEALTH | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("redis","?"))')"
    echo "   AI:     $(echo $HEALTH | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("ai_provider","?"))')"
else
    fail "后端FastAPI: 无响应或异常"
fi

# 2. 前端(via Nginx)
FRONT_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:80/ 2>/dev/null)
if [ "$FRONT_CODE" = "200" ]; then
    ok "前端(Nginx): HTTP $FRONT_CODE"
else
    fail "前端(Nginx): HTTP $FRONT_CODE"
fi

# 3. PostgreSQL
PG_RESULT=$(PGPASSWORD="huabang2024!" psql -h localhost -U huabang -d huabang_ai -c "SELECT 1" -t 2>/dev/null | tr -d ' \n')
if [ "$PG_RESULT" = "1" ]; then
    TABLE_COUNT=$(PGPASSWORD="huabang2024!" psql -h localhost -U huabang -d huabang_ai -t -c "SELECT count(*) FROM pg_tables WHERE schemaname IN ('sys','ods','dim','dwd','dws','dm','app','log','ai')" 2>/dev/null | tr -d ' ')
    ok "PostgreSQL: 连接正常 (表数量: $TABLE_COUNT)"
else
    fail "PostgreSQL: 连接失败"
fi

# 4. Redis
REDIS_RESULT=$(redis-cli -h 127.0.0.1 ping 2>/dev/null)
if [ "$REDIS_RESULT" = "PONG" ]; then
    ok "Redis: 连接正常"
else
    fail "Redis: 连接失败"
fi

# 5. Nginx
NGINX_STATUS=$(systemctl is-active nginx 2>/dev/null)
if [ "$NGINX_STATUS" = "active" ]; then
    ok "Nginx: 运行中"
else
    fail "Nginx: $NGINX_STATUS"
fi

# 6. systemd后端服务
BACKEND_STATUS=$(systemctl is-active huabang-backend 2>/dev/null)
if [ "$BACKEND_STATUS" = "active" ]; then
    ok "systemd服务: 运行中"
else
    fail "systemd服务: $BACKEND_STATUS"
fi

# 7. 最近数据同步
LAST_SYNC=$(PGPASSWORD="huabang2024!" psql -h localhost -U huabang -d huabang_ai -t -c "
SELECT to_char(max(created_at),'YYYY-MM-DD HH24:MI') FROM log.log_data_sync WHERE status='success'
" 2>/dev/null | tr -d ' ')
if [ -n "$LAST_SYNC" ] && [ "$LAST_SYNC" != "null" ]; then
    ok "最近成功同步: $LAST_SYNC"
else
    warn "最近成功同步: 无记录（可能尚未导入数据）"
fi

# 8. 最近ETL
LAST_ETL=$(PGPASSWORD="huabang2024!" psql -h localhost -U huabang -d huabang_ai -t -c "
SELECT to_char(max(started_at),'YYYY-MM-DD HH24:MI') FROM log.log_etl_run WHERE status='success'
" 2>/dev/null | tr -d ' ')
if [ -n "$LAST_ETL" ] && [ "$LAST_ETL" != "null" ]; then
    ok "最近成功ETL: $LAST_ETL"
else
    warn "最近成功ETL: 无记录（可能尚未执行ETL）"
fi

# 9. 最近钉钉推送
LAST_PUSH=$(PGPASSWORD="huabang2024!" psql -h localhost -U huabang -d huabang_ai -t -c "
SELECT to_char(max(created_at),'YYYY-MM-DD HH24:MI') FROM log.log_dingtalk_push WHERE is_success=true
" 2>/dev/null | tr -d ' ')
if [ -n "$LAST_PUSH" ] && [ "$LAST_PUSH" != "null" ]; then
    ok "最近成功推送: $LAST_PUSH"
else
    warn "最近成功推送: 无记录"
fi

# 10. 备份检查
LATEST_BACKUP=$(ls -t /srv/backups/pg/*.sql.gz 2>/dev/null | head -1)
if [ -n "$LATEST_BACKUP" ]; then
    BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 3600 ))
    if [ "$BACKUP_AGE" -lt 25 ]; then
        ok "最近备份: $(basename $LATEST_BACKUP) (${BACKUP_AGE}小时前)"
    else
        warn "最近备份: $(basename $LATEST_BACKUP) (${BACKUP_AGE}小时前，超过24小时！)"
    fi
else
    warn "备份: 尚无备份文件"
fi

echo "=========================================="
