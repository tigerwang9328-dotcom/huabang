<!-- agentmap:generated:start -->
# 前端源代码 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: frontend_app
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 前端应用 → 前端源代码
- **目录**：`frontend/src`
- **职责**：承载应用入口、路由、布局、API 客户端、状态、配置和业务视图。
- **生命周期**：`active`；**变更波动**：`high`
- **常用别名**：`src`、`财务利润导航`、`财务中心页面`

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md` 和 `frontend/AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 87 文件 / 约 14,500 行；测试 0 文件 / 0 行 / 0 个测试函数；主要语言：Vue SFC 59 个文件、TypeScript 26 个文件、JavaScript 2 个文件。
- 自动识别路由/处理器约 0 个；该数字只用于导航，不等同于稳定 API 数量。

### 关键入口与高信息量文件

- `frontend/src/main.ts`
- `frontend/src/router/index.ts`
- `frontend/src/layouts/MainLayout.vue`
- `frontend/src/config/financeCenterModules.ts`
- `frontend/src/App.vue`
- `frontend/src/views/Login.vue`
- `frontend/src/views/member/Index.vue`
- `frontend/src/views/hr/Attendance.vue`

## 直接子模块

- 无已登记的直接子模块。

## 公共接口与跨模块关系

- **接口/契约**：config/financeCenterModules.ts 集中维护 财务利润 下的旧模块、历史财务、财务中心和现金安全规划。
- **接口/契约**：views/finance/FinanceCenterModule.vue 渲染牧马人式财务中心模块说明和状态。
- **接口/契约**：views/finance/HistoricalFinance.vue 渲染金蝶历史账套、报表、余额、凭证和数据质量。
- `renders-from` → **业务 API 与数据服务**；财务页面展示后端返回的正式账簿、历史财务和数据质量状态。；证据：`frontend/src/views/finance`、`backend/app/api/v1/finance_center.py`、`backend/app/api/v1/kingdee_finance.py`；置信度：verified

## 必须保持的不变量

- 左侧导航层级保持：财务利润 -> 旧模块、历史财务、财务中心、现金安全。
- 新增财务模块先接入路由、权限、导航和空/待映射状态，再宣称可用。
- 不要删除既有财务首页、利润分析、报销、付款、费用分析和正式账簿入口。

## 修改影响检查

- 是否改变本模块职责、生命周期、入口、公共接口或数据所有权？若是，更新本文件及直接上级的子模块摘要。
- 是否改变 API、事件/任务载荷、数据库字段、租约/锁/所有权语义、错误码或状态机？若是，读取并检查所有关系模块。
- 是否只改变内部实现？若公共边界未变，不要为祖先文件制造无意义改动。
- 是否新增达到独立边界标准的子模块？满足独立运行时、独立契约、独立测试命令或约 800–1500 行以上稳定代码时，再创建下一层 `AGENTS.md`。

## 局部验证命令

- `cd frontend && npm run type-check`
- `cd frontend && npm run build`
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
