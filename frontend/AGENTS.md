<!-- agentmap:generated:start -->
# 前端应用 — 模块 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: frontend
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 作用域与职责

- **层级**：huabang-ai-center → 前端应用
- **目录**：`frontend`
- **职责**：提供 Vue 3 + Element Plus 单页应用、登录后导航、业务看板和财务中心页面。
- **生命周期**：`active`；**变更波动**：`high`
- **常用别名**：`Vue`、`Vite`、`中台页面`、`导航`

## 进入本模块时的加载规则

- 先读取仓库根 `AGENTS.md`，再读取本文件。
- 默认不要读取兄弟模块；当本模块的公共边界发生变化或任务明确跨模块时，再按“接口与关系”选择性读取。
- 修改更深层子模块时，继续读取对应子目录的 `AGENTS.md`，本文件只提供本层约束和子模块导航。

## 代码情况（自动证据）

- 本层直属范围（不含已登记子模块）：生产 6 文件 / 约 5,000 行；测试 21 文件 / 约 4,600 行 / 约 210 个测试函数；主要语言：JSON 4 个文件、TypeScript 1 个文件、JavaScript 1 个文件。
- 自动识别路由/处理器约 0 个；该数字只用于导航，不等同于稳定 API 数量。
- **关联测试目录**：`frontend/tests`

### 关键入口与高信息量文件

- `frontend/src/main.ts`
- `frontend/src/router/index.ts`
- `frontend/src/layouts/MainLayout.vue`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/public/life-data-collector.user.js`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`

## 直接子模块

| 子模块 | 路径 | 作用 | 代码情况 | 主要关联 |
|---|---|---|---|---|
| [前端源代码](src/AGENTS.md) | `frontend/src` | 承载应用入口、路由、布局、API 客户端、状态、配置和业务视图。 | 含子树 87 文件 / 约 14,500 行；生命周期 `active`；波动 `high` | renders-from→业务 API 与数据服务 |

## 公共接口与跨模块关系

- **接口/契约**：通过 src/api 调用后端 /api/v1 接口。
- **接口/契约**：通过 src/router/index.ts 定义页面路由和权限入口。
- **接口/契约**：通过 src/layouts/MainLayout.vue 和配置文件渲染左侧导航。
- `consumes-from` → **业务 API 与数据服务**；页面消费后端业务和财务接口；pending_mapping/pending_data 需要展示为待补充状态。；证据：`frontend/src/api`、`frontend/src/views/finance`、`backend/app/api/v1`；置信度：verified

## 必须保持的不变量

- 财务左侧导航必须保持历史模块不删除；新增牧马人复现模块放在 财务利润 > 财务中心 下。
- 财务导航的单一来源为 src/config/financeCenterModules.ts，避免 MainLayout 和路由重复散落配置。
- 金额、凭证摘要、往来单位和资金余额必须受财务权限保护，不能用空数据冒充无权限。

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
