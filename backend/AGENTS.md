<!-- agentmap:generated:start -->
# 后端服务 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: backend
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 后端服务
- **目录**：`backend`
- **职责**：提供 FastAPI 接口、ETL/同步、数据仓库模型、权限校验和财务中心写入能力。
- **生命周期**：`active`；**变更波动**：`high`
- **常用别名**：`FastAPI`、`API`、`服务端`、`数据仓库`

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 0 文件 / 0 行；测试 88 文件 / 约 12,000 行 / 约 540 个测试函数；主要语言：未识别。
- 自动识别路由/处理器约 0 个；该数字只用于导航，不等同于稳定 API 数量。

### 关键入口与高信息量文件

- `backend/app/main.py`

## 直接子模块

| 子模块 | 路径 | 作用 | 代码情况 | 主要关联 |
|---|---|---|---|---|
| [数据库迁移](alembic/AGENTS.md) | `backend/alembic` | 维护 PostgreSQL schema 版本、表结构、索引、约束和历史财务/正式财务中心迁移。 | 含子树 51 文件 / 约 4,300 行；生命周期 `active`；波动 `medium` | supports→业务 API 与数据服务 |
| [业务 API 与数据服务](app/AGENTS.md) | `backend/app` | 承载业务路由、模型、schema、核心配置、外部集成、ETL 服务和财务中心会计服务。 | 含子树 155 文件 / 约 38,000 行；生命周期 `active`；波动 `high` | persists-to→数据库迁移；serves→前端源代码；calls←后端脚本与批处理 |
| [后端脚本与批处理](scripts/AGENTS.md) | `backend/scripts` | 存放一次性导入、同步、校验、报表或维护脚本，服务于后端数据落库和运维验证。 | 含子树 13 文件 / 约 1,400 行；生命周期 `active`；波动 `medium` | calls→业务 API 与数据服务 |

## 公共接口与跨模块关系

- **接口/契约**：通过 app/api/v1 暴露业务 API，统一返回 ApiResponse。
- **接口/契约**：通过 SQLAlchemy/Alembic 维护 PostgreSQL 的 ods/dim/dwd/dws/dm/fin/sys/app 等 schema。
- **接口/契约**：通过集成模块同步百胜、钉钉、金蝶历史财务等外部来源。
- `serves` → **前端应用**；前端通过 /api/v1 调用后端业务和财务接口；权限不足必须返回明确错误而非空数据。；证据：`backend/app/api/v1`、`frontend/src/api`；置信度：verified
- `deployed-by` → **部署与运维**；生产发布使用 deploy 脚本和 SSH 到 /srv/huabang-ai-center；重启需用户授权。；证据：`deploy`、`AGENTS.md`；置信度：declared

## 必须保持的不变量

- 数据库迁移必须保持单一 Alembic head。
- 业务数据写入必须经过服务层权限和幂等约束，不直接在 API 层拼写持久化细节。
- 生产迁移前先备份数据库；未获授权不得重启生产服务。

## 修改影响检查

- 是否改变本模块职责、生命周期、入口、公共接口或数据所有权？若是，更新本文件及直接上级的子模块摘要。
- 是否改变 API、事件/任务载荷、数据库字段、租约/锁/所有权语义、错误码或状态机？若是，读取并检查所有关系模块。
- 是否只改变内部实现？若公共边界未变，不要为祖先文件制造无意义改动。
- 是否新增达到独立边界标准的子模块？满足独立运行时、独立契约、独立测试命令或约 800–1500 行以上稳定代码时，再创建下一层 `AGENTS.md`。

## 局部验证命令

- `cd backend && pytest`
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
