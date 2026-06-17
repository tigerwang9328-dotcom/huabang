#!/bin/bash
# PostgreSQL 每日自动备份脚本
BACKUP_DIR="/srv/backups/pg"
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="huabang_ai"
DB_USER="huabang"
PGPASSWORD="huabang2024!"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"

echo "[$(date)] 开始备份 $DB_NAME..."
PGPASSWORD="$PGPASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] 备份成功: $BACKUP_FILE ($SIZE)"
    # 清理超过KEEP_DAYS天的旧备份
    find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$KEEP_DAYS -delete
    echo "[$(date)] 已清理 ${KEEP_DAYS} 天前的旧备份"
else
    echo "[$(date)] 备份失败！" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi
