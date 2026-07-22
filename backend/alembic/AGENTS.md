<!-- agentmap:generated:start -->
# 数据库迁移 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: backend_migrations
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 后端服务 → 数据库迁移
- **目录**：`backend/alembic`
- **职责**：维护 PostgreSQL schema 版本、表结构、索引、约束和历史财务/正式财务中心迁移。
- **生命周期**：`active`；**变更波动**：`medium`
- **常用别名**：`Alembic`、`schema`、`迁移脚本`

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md` 和 `backend/AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 51 文件 / 约 4,300 行；测试 0 文件 / 0 行 / 0 个测试函数；主要语言：Python 51 个文件。
- 自动识别路由/处理器约 0 个；该数字只用于导航，不等同于稳定 API 数量。

### 关键入口与高信息量文件

- `backend/alembic/env.py`
- `backend/alembic/versions/3e1f6a7b8c97_full_finance_center.py`
- `backend/alembic/versions/1f0a2b3c4d5e_task_workflow_notifications.py`
- `backend/alembic/versions/2a0f6a7b8c93_investment_decision_history.py`
- `backend/alembic/versions/1b10a07bbe68_add_dingtalk_finance_hr_tables.py`
- `backend/alembic/versions/e6f7a8b9c0d1_boss_command_center.py`
- `backend/alembic/versions/f1b2c3d4e5f6_life_data_collector.py`
- `backend/alembic/versions/0b8c9d0e1f2a_business_exception_evidence.py`

## 直接子模块

- 无已登记的直接子模块。

## 公共接口与跨模块关系

- **接口/契约**：由 alembic.ini 和 env.py 驱动数据库迁移。
- **接口/契约**：迁移脚本必须与 app/models 中的持久化对象和服务层 SQL 兼容。
- `supports` → **业务 API 与数据服务**；为后端模型、API 和导入服务提供持久化结构。；证据：`backend/app/models`、`backend/alembic/versions`；置信度：verified

## 必须保持的不变量

- 任何新增迁移后必须验证 Alembic 为单一 head。
- 正式上线迁移必须先备份生产库；失败时报告实际错误，不隐藏异常。

## 修改影响检查

- 是否改变本模块职责、生命周期、入口、公共接口或数据所有权？若是，更新本文件及直接上级的子模块摘要。
- 是否改变 API、事件/任务载荷、数据库字段、租约/锁/所有权语义、错误码或状态机？若是，读取并检查所有关系模块。
- 是否只改变内部实现？若公共边界未变，不要为祖先文件制造无意义改动。
- 是否新增达到独立边界标准的子模块？满足独立运行时、独立契约、独立测试命令或约 800–1500 行以上稳定代码时，再创建下一层 `AGENTS.md`。

## 局部验证命令

- `cd backend && alembic heads`
- `cd backend && alembic upgrade head`
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
