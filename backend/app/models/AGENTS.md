# backend/app/models — SQLAlchemy ORM 模型

<!-- agentmap:generated:start -->
## 范围

SQLAlchemy ORM 模型,按数据仓库与业务域分层。**不负责**:业务查询逻辑、API 序列化。

## 分层与关键文件

- `__init__.py` — **统一导出所有模型**,Alembic autogenerate 依赖此导入;新增模型必须在此 re-export
- `sys.py` — 系统权限:SysUser/Department/Role/Menu/Permission/UserRole/RolePermission/FieldPermission/DingtalkBind/Dict/IntegrationConfig/Param/UserStore
- `log.py` — LogDataSync/DataQuality/AiCall/DingtalkPush/UserLogin/UserOperation/Export/Error
- `app.py` — AppActionTask/TaskFeedback/TaskReview/ManualTarget/WarningConfig/PushTemplate/AiPromptTemplate
- `ods.py` — OdsBaison*(Store/Product/Sku/SalesOrder/SalesDetail/ReturnOrder/ReturnDetail/Inventory/Member/Employee)原始落档
- `dim.py` — DimStore/Product/Sku/Member/Employee/Date/BaisonShop/Warehouse 维度
- `dwd.py` — DwdSalesDetail/ReturnDetail/InventorySnapshot/FinanceExpense/FinanceCash 明细(含 `dwd_pos_ticket` 退货取负)
- `dws.py` — DwsStoreDailySales/CompanyDaily/InventoryDaily/ProductDaily/FinanceDaily 日汇总
- `dm.py` — DmBossDailyReport/StoreDiagnosis/InventoryWarning/ExceptionAudit/MemberVisitList/ReplenishmentAdvice/FinanceProfitDaily 老板看板与诊断
- `finance_core.py` + `finance_operations.py` — **正式可写财务账簿** `fin.*` 表(账簿/期间/科目/凭证/分录/版本/余额/报表映射/应收应付/资金/发票/工资/税务)
- `kingdee_finance.py` — **金蝶历史只读**链路表(账套/科目/凭证/分录/余额/来源链接)
- `dingtalk_attendance.py` / `dingtalk_event.py` / `dingtalk_hr_finance.py` — 钉钉落档
- `ai.py` — AiAssistantConversation/Message/BusinessAdviceSnapshot/DiagnosisResult/RuleMatch
- `life_data.py` — 生意经采集
- `baison_ods.py` / `baison_dwd.py` — 百胜扩展落档(若与 ods/dwd 并存)

## 本地状态与失败行为

- 模型与 DB schema 偏差:Alembic autogenerate 会检测,必须生成迁移对齐
- `__init__.py` 漏导出:autogenerate 看不到该表,迁移缺失

## 公共输入/输出

- 所有模型继承 `core.database.Base`
- 主键统一 `id`(BigInteger 自增),业务键带唯一约束
- 时间字段 `created_at`/`updated_at` 默认 now

## 模块不变量

1. **分层契约**:ods=原始落档(只增不改)/ dim=维度 / dwd=明细 / dws=日汇总 / dm=老板看板与诊断。同层不跨层写。
2. **金蝶历史只读**:`kingdee_finance.py` 表只由迁移脚本写入;正式账簿写 `fin.*` 表(`finance_core`/`finance_operations`)。任何业务代码不得写 kingdee_*。
3. **dwd_pos_ticket 退货取负**:`lx='ls'` 正数,`lx='lt'` 负数(sales_amount/sales_qty/standard_amount/gross_profit_source_amount)。ETL 必须按 lx 处理。
4. `__init__.py` 统一导出所有模型,Alembic autogenerate 依赖此导入。
5. 新增表必须配 Alembic 迁移;禁止裸 SQL 建表入生产。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_kingdee_finance_models.py tests/test_finance_center_models.py tests/test_life_data_models.py tests/test_investment_decision_models.py -q
.venv/bin/alembic heads
```
<!-- agentmap:generated:end -->

## 手动备注

`dwd_pos_ticket` 的 `lx` 字段是历史踩坑点(7/15 门店 185805 退货被当销售致虚高 1870 元);任何改 dwd 的 ETL 必须回归 `test_dws_to_dm_refunds.py` 与 `test_pos_ticket_sync_completeness.py`。
