<!-- agentmap:generated:start -->
# 后端脚本与批处理 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: backend_scripts
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 后端服务 → 后端脚本与批处理
- **目录**：`backend/scripts`
- **职责**：存放一次性导入、同步、校验、报表或维护脚本，服务于后端数据落库和运维验证。
- **生命周期**：`active`；**变更波动**：`medium`
- **常用别名**：`导入脚本`、`ETL 脚本`、`补采脚本`

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md` 和 `backend/AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 13 文件 / 约 1,400 行；测试 0 文件 / 0 行 / 0 个测试函数；主要语言：Python 13 个文件。
- 自动识别路由/处理器约 0 个；该数字只用于导航，不等同于稳定 API 数量。

### 关键入口与高信息量文件

- `backend/scripts/import_kingdee_finance.py`
- `backend/scripts/seed_module_permissions.py`
- `backend/scripts/init_db.py`
- `backend/scripts/export_ai_business_advice_context.py`
- `backend/scripts/sync_baison_member_deposits.py`
- `backend/scripts/generate_boss_command_center.py`
- `backend/scripts/sync_baison_product_inbound.py`
- `backend/scripts/backfill_investment_metrics.py`

## 直接子模块

- 无已登记的直接子模块。

## 公共接口与跨模块关系

- **接口/契约**：脚本可调用后端模型、数据库连接和服务层逻辑完成批处理。
- **接口/契约**：对生产数据有写入影响的脚本必须先在测试库或 worktree 验证。
- `calls` → **业务 API 与数据服务**；批处理复用后端配置、模型和服务，不绕过业务不变量。；证据：`backend/scripts`、`backend/app/services`；置信度：inferred

## 必须保持的不变量

- 脚本不得静默跳过失败；涉及导入、哈希、行数或财务校验时必须输出可追溯结果。
- 不得删除未验证备份、源快照或迁移结果文件。

## 修改影响检查

- 是否改变本模块职责、生命周期、入口、公共接口或数据所有权？若是，更新本文件及直接上级的子模块摘要。
- 是否改变 API、事件/任务载荷、数据库字段、租约/锁/所有权语义、错误码或状态机？若是，读取并检查所有关系模块。
- 是否只改变内部实现？若公共边界未变，不要为祖先文件制造无意义改动。
- 是否新增达到独立边界标准的子模块？满足独立运行时、独立契约、独立测试命令或约 800–1500 行以上稳定代码时，再创建下一层 `AGENTS.md`。

## 局部验证命令

- 尚未配置；从 CI、包管理文件或现有文档核验后补充。
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
