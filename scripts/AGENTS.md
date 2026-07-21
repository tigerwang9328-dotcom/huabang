# scripts — crontab 调度脚本

<!-- agentmap:generated:start -->
## 范围

crontab 调度的 shell 脚本:数据同步、备份、快照生成、健康检查。**不负责**:Python 业务逻辑(在 backend)、前端构建。

## 关键脚本(按业务域)

### 数据同步(百胜 E3ERP)
- `sync_pos_tickets_daily.sh` — **每日北京时间 04:00**(crontab `0 20 * * *` UTC)拉取最近 7 天小票,记 `log.log_etl_run`,调 `pos_ticket_service`
- `sync_baison_inventory_daily.sh` — 库存同步(每日 21:30 + 日内 02/04/06/.../14 点,`flock` 加锁)
- `sync_baison_master_daily.sh` — 主数据同步(每日 18:30)
- `sync_baison_members_daily.sh` — 会员同步(每日 19:00,`flock`)
- `sync_baison_member_deposits_daily.sh` — 储值同步(每日 19:15,`flock`)
- `sync_baison_product_inbound_daily.sh` — 入库同步(每日 19:30,`flock`)
- `sync_baison_store_targets_daily.sh` — 门店目标同步(每日 20:30,`flock`)
- `rebuild_pos_sale_goods_from_tickets.sh` — 从小票重建销售商品(含成本)

### 快照生成
- `generate_boss_command_center_daily.sh` — 老板指挥台每日快照(22:30,`flock`)
- `generate_size_wall_snapshot_daily.sh` — 尺码墙快照(22:00,`flock`)
- `generate_ai_business_advice_daily.sh` — AI 经营建议每日(22:45,`flock`)

### 备份与运维
- `pg_backup.sh` — PostgreSQL 每日备份(03:00 UTC = 北京 11:00),保留 7 天,`/srv/backups/pg/`
- `git_daily_backup.sh` — Git 每日提交推送 GitHub(03:30 UTC)
- `health_check.sh` — 健康检查

## crontab(用户 xiaohu,服务器 UTC 时区)

```
0  3 * * *  pg_backup.sh                                    # 北京 11:00
30 3 * * *  git_daily_backup.sh                             # 北京 11:30
0 20 * * *  sync_pos_tickets_daily.sh                       # 北京 04:00
30 18 * * * sync_baison_master_daily.sh                     # 北京 02:30
30 21 * * * sync_baison_inventory_daily.sh                  # 北京 05:30
0  2,4,6,8,10,12,14 * * * sync_baison_inventory_daily.sh    # 日内库存
0 19 * * *  sync_baison_members_daily.sh                    # 北京 03:00
30 19 * * * sync_baison_product_inbound_daily.sh            # 北京 03:30
15 19 * * * sync_baison_member_deposits_daily.sh            # 北京 03:15
30 20 * * * sync_baison_store_targets_daily.sh              # 北京 04:30
0  22 * * * generate_size_wall_snapshot_daily.sh            # 北京 06:00
30 22 * * * generate_boss_command_center_daily.sh           # 北京 06:30
45 22 * * * generate_ai_business_advice_daily.sh            # 北京 06:45
```

## 本地状态与失败行为

- `set -e`:同步脚本失败即退出,记 `log_etl_run.status=failed`
- `flock -n`:并发实例被拒,日志记录锁冲突
- DB 凭证:从 `backend/.env` grep `DB_USER`/`DB_PASSWORD`,以 `PGPASSWORD` 调 psql
- 日志:`/srv/huabang-ai-center/logs/*.log`

## 公共输入/输出

- 入参:无(基于当前日期计算窗口),或环境变量
- 出参:写 backend DB(经 `.venv/bin/python` 内联脚本) + 日志文件
- 凭证:`backend/.env`(grep 解析)

## 模块不变量

1. **并发敏感脚本必须用 `flock -n` 加锁**(库存/会员/入库/储值/目标/尺码墙/指挥台/AI 建议)。
2. **crontab 时区为服务器 UTC**;北京时间 = UTC + 8(如 `0 20 * * *` = 北京 04:00)。
3. 脚本以 `xiaohu` 身份运行,路径硬编码 `/srv/huabang-ai-center/`。
4. `pg_backup` 每日 03:00 UTC(北京 11:00)备份,保留 7 天;`git_daily_backup` 03:30 UTC。
5. 同步脚本写 `log.log_etl_run`(task_name/started_at/status),便于追踪。

## 焦点测试/构建命令

```bash
# 查看当前 crontab
crontab -l | grep -v '^#' | grep -v '^$'

# 手动跑一次(示例)
ssh -o BatchMode=yes xiaohu@100.94.89.49 "cd /srv/huabang-ai-center && bash scripts/sync_pos_tickets_daily.sh 2>&1 | tail -20"

# 查最近同步日志
ssh -o BatchMode=yes xiaohu@100.94.89.49 "tail -30 /srv/huabang-ai-center/logs/sync_tickets_daily.log"
```
<!-- agentmap:generated:end -->

## 手动备注

`pg_backup.sh` 内硬编码了 DB 密码 `huabang2024!`(历史遗留,敏感)— 改密必须同步更新此脚本与 `backend/.env`。脚本目录有多个 `.bak_*` 备份(如 `sync_baison_inventory_daily.sh.bak_cost_20260710`),勿误用。改同步窗口必须同时考虑与 APScheduler(Asia/Shanghai)任务不冲突。
