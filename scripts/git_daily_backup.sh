#!/bin/bash
set -e

cd /srv/huabang-ai-center

LOG_FILE="/srv/huabang-ai-center/scripts/git_daily_backup.log"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始每日GitHub备份 =====" >> "$LOG_FILE"

git add .

if git diff --cached --quiet; then
  echo "没有代码变化，本次不提交。" >> "$LOG_FILE"
else
  git commit -m "backup: 每日服务器代码备份 $(date '+%Y-%m-%d %H:%M')"
  git push
  echo "备份完成，已推送到GitHub。" >> "$LOG_FILE"
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 备份任务结束 =====" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
