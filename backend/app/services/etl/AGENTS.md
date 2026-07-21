# backend/app/services/etl — ETL 管线

<!-- agentmap:generated:start -->
## 范围

ETL 管线 `ODS → DWD → DWS → DM`,带 `etl_log` 记录每步行数与状态。**不负责**:从第三方 API 拉数到 ods(在 integrations/baison)、调度触发(在 jobs)。

## 关键文件

- `pipeline.py` — `ETLPipeline` 总调度,`STEP_ORDER = ["ods_to_dwd","dwd_to_dws","dws_to_dm"]`,`run_full(stat_date)` / `run_step(step, stat_date)`
- `ods_to_dwd.py` — 原始落档 → 明细(清洗/标准化/退货取负)
- `dwd_to_dws.py` — 明细 → 日汇总(**必须按 store_whitelist 过滤**)
- `dws_to_dm.py` — 日汇总 → 老板看板/诊断(按 stat_date 幂等覆盖 `dm_boss_daily_report`)
- `etl_log.py` — `ETLLogger` 记录 run_id/step/rows/status

## 本地状态与失败行为

- 前步失败 → 后步不跑,overall = `partial` 或 `failed`
- 单步异常:`etl_log.fail_task` 记录 traceback,`db.rollback()`,返回 `{status:failed, error}`
- 全成功:overall = `success`,每步返回 rows 字典

## 公共输入/输出

- 入参:`stat_date`(YYYY-MM-DD,默认昨天)、`db`(AsyncSession)
- 出参:`{stat_date, steps:[{step,status,rows,error}], status:"success"|"partial"|"failed"}`
- 读:ods.*/dim.* → 写 dwd.* → 读 dwd.* → 写 dws.* → 读 dws.* → 写 dm.*

## 消费者/生产者

- **消费**:`backend_models`(各层 ORM)、`backend_core`(store_whitelist 过滤口径)
- **生产**:`backend_jobs.sync_jobs`(触发 `run_full`)、`scripts/rebuild_pos_sale_goods_from_tickets.sh`(重建)

## 模块不变量

1. `STEP_ORDER` 不可乱序,前步失败后步不跑。
2. `dwd_to_dws` 必须按 `store_whitelist` 过滤;退货(`lt`)在 dwd 已取负,dws 直接 `SUM`。
3. `dws_to_dm` 重建 `dm_boss_daily_report` 时按 `stat_date` 幂等覆盖,不累积。
4. `etl_log` 记录 `run_id`/`step`/`rows`/`status`;失败必须 rollback 并 `fail_task`。
5. ods 层只增不改;dwd 退货记录的金额/数量必须为负。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_dws_to_dm_refunds.py tests/test_pos_ticket_sync_completeness.py tests/test_pos_sale_goods_cost_rebuild.py tests/test_sales_channel_split.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

退货取负是历史踩坑点:`dwd_pos_ticket` 中 `lx='lt'` 必须负数,否则 dws `SUM` 后销售额虚高。改 `dwd_to_dws` 过滤逻辑必须同步审查 `store_whitelist` 并重建受影响日期的 dws/dm(脚本 `scripts/rebuild_pos_sale_goods_from_tickets.sh`)。
