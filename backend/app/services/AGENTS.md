# backend/app/services — 业务服务层

<!-- agentmap:generated:start -->
## 范围

30+ 业务 service,覆盖经营概览/报告/会员/商品/库存/投流/任务/AI 诊断/指挥台/规则引擎/财务中心/金蝶/钉钉/利润/尺码墙。子模块 `etl/` 单列(见其 AGENTS.md)。**不负责**:HTTP 路由处理、第三方 API 原始封装(在 integrations)、调度注册(在 jobs)。

## 关键文件(按业务域)

- **经营报告**:`report_service.py`(522 行,经营日报)、`business_overview_service.py`(经营概览,按 10 库存白名单统计库存)、`metrics.py`、`sales_metric_service.py`
- **指挥台**:`command_center_service.py`(老板指挥台)、`command_center_health_service.py`(每日健康检查,只生成幂等任务草稿)、`exception_rule_service.py`、`rule_engine.py`(464 行)
- **财务(正式可写)**:`finance_center_service.py`(`/api/v1/finance-center` 正式账簿写入)、`kingdee_finance_service.py`(金蝶历史只读)
- **财务分析**:`profit_service.py`(利润)、`dingtalk_budget_service.py`(预算)
- **AI**:`ai_engine.py`(LLM 引擎)、`ai_assistant_service.py`(老板聊天助手,只读)、`ai_diagnosis_service.py`(自动诊断)、`ai_business_advice_service.py`(经营建议快照)
- **会员**:`member_action_service.py`、`member_sales_service.py`、`member_segment_service.py`
- **商品/库存**:`product_analysis_service.py`、`inventory_analysis_service.py`(按 10 库存白名单)、`size_wall_service.py`(637 行,尺码墙快照)、`store_analysis_service.py`
- **投流决策**:`investment_decision_service.py`、`investment_environment_service.py`、`investment_metric_service.py`、`performance_attribution_service.py`
- **任务**:`task_workflow_service.py`、`task_notification_service.py`(578 行,钉钉推送预算控制)
- **校验/规则**:`validation_service.py`、`rule_engine.py`
- **第三方封装**:`dingtalk.py`(出站钉钉)、`baison_import.py`(百胜导入)
- **任务通知**:`task_notification_service.py`(推送预算/claims 校验)

## 本地状态与失败行为

- service 经 `get_db` 注入 AsyncSession,异常向上抛由路由 handler 处理
- LLM 调用失败:ai_engine 降级返回空建议,不阻塞主流程
- 钉钉推送超预算:`task_notification_service` 拒绝发送并落日志

## 公共输入/输出

- 入参:AsyncSession + 业务参数(日期/门店/过滤条件)
- 出参:ORM 对象 / dataclass / dict(经 schema 序列化)
- 副作用:写 dws/dm/fin/ai/log 表,绝不写 ods/dim/kingdee_*

## 模块不变量

1. service 只通过 `get_db` 注入的 AsyncSession 操作 DB;不自行 create_engine。
2. **金蝶历史源只读**;正式可写财务走 `finance_center_service` → `fin.*` 表,不写回金蝶服务器与原始快照。
3. **月度报表缺映射返回 `pending_mapping`**,不把缺失显示为 0 或 ready。
4. **AI 经营建议与投流决策对事实层只读**;LLM 输出不直接落 dws/dm 事实表,仅落 `ai.*` 快照。
5. 推送类 service 受 `DINGTALK_MAX_PUSH_PER_HOUR` 限流,超限拒绝。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_report_service.py tests/test_command_center_service.py tests/test_finance_center_service.py tests/test_kingdee_finance_service.py tests/test_profit_service.py tests/test_ai_diagnosis_*.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

`business_overview_service` / `inventory_analysis_service` 的库存口径必须用 10 个库存白名单编码(7 门店 + GZ001/GZ002/GYNG),与销售的 7 门店口径区分。改 `finance_center_service` 必须配 Alembic 迁移并跑 `test_finance_center_*` 三件套。
