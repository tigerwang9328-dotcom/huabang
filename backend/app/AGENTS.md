<!-- agentmap:generated:start -->
# 业务 API 与数据服务 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: backend_app
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 后端服务 → 业务 API 与数据服务
- **目录**：`backend/app`
- **职责**：承载业务路由、模型、schema、核心配置、外部集成、ETL 服务和财务中心会计服务。
- **生命周期**：`active`；**变更波动**：`high`
- **常用别名**：`app`、`正式财务中心`、`金蝶历史财务`、`百胜同步`、`钉钉同步`

### 不负责

- 不直接负责前端导航展示。
- 不直接执行生产服务重启。

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md` 和 `backend/AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 155 文件 / 约 38,000 行；测试 88 文件 / 约 12,000 行 / 约 540 个测试函数；主要语言：Python 155 个文件。
- 自动识别路由/处理器约 402 个；该数字只用于导航，不等同于稳定 API 数量。
- **关联测试目录**：`backend/tests`

### 关键入口与高信息量文件

- `backend/app/main.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/finance_center.py`
- `backend/app/api/v1/kingdee_finance.py`
- `backend/app/models/app.py`
- `backend/app/services/ai_diagnosis_service.py`
- `backend/app/services/command_center_service.py`
- `backend/app/services/finance_center_service.py`

## 直接子模块

- 无已登记的直接子模块。

## 公共接口与跨模块关系

- **接口/契约**：app/api/v1/finance_center.py 提供可写正式财务中心接口，包括凭证、期间、报表映射和金蝶历史写入。
- **接口/契约**：app/api/v1/kingdee_finance.py 提供只读历史财务查询接口。
- **接口/契约**：app/core/store_whitelist.py 是销售和库存白名单口径的源头。
- `serves` → **前端源代码**；财务页面消费 /api/v1/finance 和 /api/v1/finance-center；缺映射、缺期间和非正式数据必须显式标识。；证据：`backend/app/api/v1/finance_center.py`、`backend/app/api/v1/kingdee_finance.py`、`frontend/src/views/finance`；置信度：verified
- `persists-to` → **数据库迁移**；模型和服务的持久化结构必须由 Alembic 迁移声明并保持单一 head。；证据：`backend/app/models`、`backend/alembic/versions`；置信度：verified

## 必须保持的不变量

- 历史金蝶快照不得被覆盖；写入正式账簿时保留 source_system、source_database、source_pk、import_batch_id 等来源追踪。
- 凭证写入必须借贷平衡，正式分录保持单边非负，过账、冲销、修订需写操作日志。
- 现有 dwd_finance_expense、dwd_finance_cash 不由金蝶历史导入直接覆盖。

## 修改影响检查

- 是否改变本模块职责、生命周期、入口、公共接口或数据所有权？若是，更新本文件及直接上级的子模块摘要。
- 是否改变 API、事件/任务载荷、数据库字段、租约/锁/所有权语义、错误码或状态机？若是，读取并检查所有关系模块。
- 是否只改变内部实现？若公共边界未变，不要为祖先文件制造无意义改动。
- 是否新增达到独立边界标准的子模块？满足独立运行时、独立契约、独立测试命令或约 800–1500 行以上稳定代码时，再创建下一层 `AGENTS.md`。

## 局部验证命令

- `cd backend && pytest tests/test_finance_center_api.py tests/test_finance_center_models.py tests/test_finance_center_service.py tests/test_import_kingdee_finance.py`
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
