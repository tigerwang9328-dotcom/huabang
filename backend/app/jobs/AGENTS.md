# backend/app/jobs — APScheduler 定时任务

<!-- agentmap:generated:start -->
## 范围

APScheduler 定时任务注册与执行。**不负责**:任务业务实现(在 services)、shell 脚本调度(在项目根 `scripts/`)。

## 关键文件

- `scheduler.py` — `AsyncIOScheduler`(timezone=Asia/Shanghai,MemoryJobStore);`setup_jobs()` 在 FastAPI lifespan 调用,注册全部定时任务
- `sync_jobs.py` — `run_daily_sync`(每日 01:00 同步百盛+ETL)、`run_dingtalk_approval_sync`、`run_dingtalk_attendance_sync`
- `report_jobs.py` — `run_morning_report`(08:30 老板日报)
- `command_center_health_jobs.py` — `run_command_center_health_monitor`(06:40 经营指挥台健康检查)
- `push_jobs.py` — `run_member_visit_push`(10:00 会员回访)、`run_overdue_reminder`(18:00 任务逾期)、`run_replenishment_push`(14:00 补货)、`run_task_assignment_notifications`
- `review_jobs.py` — `run_evening_diagnosis`(晚间诊断)
- `life_data_jobs.py` — `cleanup_life_data_captures`、`mark_stale_life_data_collectors_offline`
- `investment_decision_jobs.py` — `capture_due_outcomes`、`run_daily_investment_summary`、`run_investment_period_generation`
- `ai_assistant_jobs.py` — `cleanup_ai_assistant_conversations`(30 天保留)

## 主要调度时刻(Asia/Shanghai)

| 时刻 | 任务 | misfire_grace |
| --- | --- | --- |
| 01:00 | 每日数据同步+ETL | 3600s |
| 06:40 | 经营指挥台健康检查 | 1800s |
| 08:30 | 早间老板日报 | 1800s |
| 09/13/18/23:05 | 钉钉考勤同步 | 1800s |
| 10:00 | 会员回访名单推送 | 1800s |
| 12:00 | 钉钉审批同步 | 3600s |
| 14:00 | 补货调拨提醒 | 1800s |
| 18:00 | 任务逾期提醒 | — |
| 晚间 | 诊断 | — |

## 消费者/生产者

- **消费**:`backend_services`(业务)、`backend_services_etl`(ETL 管线)
- **生产**:写 dws/dm/ai/log,触发钉钉推送

## 模块不变量

1. `scheduler` 时区 Asia/Shanghai;`MemoryJobStore`(重启即丢,任务幂等设计)。
2. `setup_jobs()` 在 FastAPI lifespan 启动时调用;每个任务 `replace_existing=True`。
3. 任务失败不阻塞调度器;关键任务 `misfire_grace_time` 兜底。
4. **命令中心健康检查只生成待人工确认的幂等任务草稿**,不依赖钉钉开关。
5. 考勤同步 `coalesce=True` + `max_instances=1`,防止堆积。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_investment_decision_jobs.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

调度时刻均为 Asia/Shanghai(北京时间)。注意与 `scripts/` 下 crontab(UTC)区分:crontab `0 20 * * *` = 北京 04:00 拉小票。两者互补:crontab 跑 shell 同步,APScheduler 跑 Python 业务任务。
