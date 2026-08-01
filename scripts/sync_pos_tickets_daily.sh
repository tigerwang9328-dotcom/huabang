#!/bin/bash
# 华邦 POS 小票每日同步:每天北京时间04:00拉取最近7天数据
# 由 cron.daily 调度;日志写入 /srv/huabang-ai-center/logs/sync_tickets_daily.log
set -e

BACKEND_DIR="/srv/huabang-ai-center/backend"
LOG_DIR="/srv/huabang-ai-center/logs"
LOG_FILE="$LOG_DIR/sync_tickets_daily.log"
TASK_NAME="pos_ticket_daily"

mkdir -p "$LOG_DIR"

START_TS=$(TZ='Asia/Shanghai' date -d '6 days ago' '+%Y-%m-%d 00:00:00')
END_TS=$(TZ='Asia/Shanghai' date '+%Y-%m-%d 23:59:59')

echo "==========================================" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始同步 $START_TS ~ $END_TS" | tee -a "$LOG_FILE"

cd "$BACKEND_DIR"

DB_HOST=$(grep '^DB_HOST=' .env | cut -d= -f2-)
DB_PORT=$(grep '^DB_PORT=' .env | cut -d= -f2-)
DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2-)
DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2-)
DB_PASS=$(grep '^DB_PASSWORD=' .env | cut -d= -f2-)
DB_HOST=${DB_HOST:-localhost}; DB_PORT=${DB_PORT:-5432}; DB_NAME=${DB_NAME:-huabang_ai}
PGPASSFILE=$(mktemp)
trap 'rm -f "$PGPASSFILE"' EXIT
chmod 600 "$PGPASSFILE"
printf '%s:%s:%s:%s:%s\n' "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASS" > "$PGPASSFILE"
export PGPASSFILE
unset DB_PASS

ETL_ID=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -A -q -c \
  "INSERT INTO log.log_etl_run(task_name, started_at, status) VALUES ('${TASK_NAME}', now(), 'running') RETURNING id;" 2>/dev/null | head -n1 | tr -d '[:space:]')
echo "ETL run id: ${ETL_ID:-<none>}" >> "$LOG_FILE"

set +e
./.venv/bin/python - <<PY_EOF >> "$LOG_FILE" 2>&1
import asyncio, sys, json
sys.path.insert(0, '.')
from app.core.database import AsyncSessionLocal
from app.integrations.baison.services.pos_ticket_service import PosTicketService

START_TS = "${START_TS}"
END_TS   = "${END_TS}"

async def main():
    service = PosTicketService()
    async with AsyncSessionLocal() as db:
        try:
            result = await service.sync_range(START_TS, END_TS, max_pages=0, page_size=100)
            await db.commit()
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as e:
            await db.rollback()
            print(f"FAIL: {e.__class__.__name__}: {e}", file=sys.stderr)
            sys.exit(1)

asyncio.run(main())
PY_EOF
RC=$?
set -e

if [ $RC -eq 0 ]; then
  set +e
  /srv/huabang-ai-center/scripts/rebuild_pos_sale_goods_from_tickets.sh "$START_TS" "$END_TS" >> "$LOG_FILE" 2>&1
  REBUILD_RC=$?
  set -e
  if [ $REBUILD_RC -eq 0 ]; then
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
      "UPDATE log.log_etl_run SET finished_at=now(), status='success' WHERE id=${ETL_ID};" \
      >> "$LOG_FILE" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 同步成功 rc=$RC rebuild_rc=$REBUILD_RC" | tee -a "$LOG_FILE"
  else
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
      "UPDATE log.log_etl_run SET finished_at=now(), status='failed', error_msg='商品明细重建失败' WHERE id=${ETL_ID};" \
      >> "$LOG_FILE" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 商品明细重建失败 rc=$REBUILD_RC" | tee -a "$LOG_FILE"
    exit $REBUILD_RC
  fi
else
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
    "UPDATE log.log_etl_run SET finished_at=now(), status='failed', error_msg='同步脚本返回非0' WHERE id=${ETL_ID};" \
    >> "$LOG_FILE" 2>&1
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 同步失败 rc=$RC" | tee -a "$LOG_FILE"
  exit $RC
fi
