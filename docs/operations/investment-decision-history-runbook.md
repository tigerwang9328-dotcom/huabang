# 投流决策历史数据库上线运行手册

## 上线边界

- 本功能只读取抖音来客生意经数据、生成建议并记录人工决定、实际执行和结果。
- DeepSeek 不得直接修改投放预算；所有建议均保持 `requires_human_confirm=true`。
- “投放人群地域消耗分布（按居住地）”只说明广告消耗流向，不能单独判断地域效果。

## 上线前检查

1. 确认生产代码目录没有待处理的 Alembic 多头；新迁移 revision 为 `2a0f6a7b8c93`。
2. 执行 `alembic heads`，必须只有一个 head；若生产分支已有新迁移，先创建 merge migration，禁止强行改写已应用 revision。
3. 配置 `INVESTMENT_AI_ENABLED`、`INVESTMENT_AI_MODEL`、`INVESTMENT_AI_TIMEOUT_SECONDS`、`INVESTMENT_AI_MIN_INTERVAL_MINUTES` 和 `INVESTMENT_AI_MAX_BUDGET_FEN`。
4. 先保持 `INVESTMENT_AI_ENABLED=false`，完成迁移和规则兜底验证后再开启 DeepSeek。

## 数据迁移与回填

```bash
cd /srv/huabang-ai-center/backend
source .venv/bin/activate
alembic upgrade head
PYTHONPATH=. python scripts/backfill_investment_metrics.py
PYTHONPATH=. python scripts/backfill_investment_metrics.py --apply
```

默认回填命令只输出候选数量，不写数据库；确认账户、周期和字段口径后才使用 `--apply`。相同 `input_hash` 冲突时跳过，允许重复执行。

## 验收

1. `/api/v1/investment-decisions/overview` 能返回规则或 DeepSeek 来源。
2. `/history` 能返回建议、人工决定、实际执行和结果窗口。
3. 页面刷新不重复调用模型；相同输入哈希复用历史结果。
4. 人工采纳后仍显示未执行；只有登记正数实际预算后才显示已执行。
5. 24、72、168 小时结果分别只读取对应截止时间前的快照。
6. 省份和城市分栏展示，页面不再出现“贵阳及周边消耗分布”。

## 监控与降级

- 关注 `log_ai_call.call_type=investment_decision` 的状态、耗时和错误信息。
- DeepSeek 超时、输出越界、频控或数据缺失时自动使用确定性规则建议。
- 紧急降级只需设置 `INVESTMENT_AI_ENABLED=false`；历史查询、人工流程和结果采集继续运行。

## 回滚

- 应用回滚：回退后端和前端版本，保留新增历史表，避免丢失人工决定和执行记录。
- 数据库降级仅在确认六张历史表没有需保留数据时执行；生产环境不建议自动执行 `alembic downgrade`。
- 若调度异常，先禁用对应 APScheduler 任务，再检查锁文件、日志和数据库记录；不要删除历史数据来恢复任务。
