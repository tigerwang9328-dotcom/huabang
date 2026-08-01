# 牧马人财务模块直接移植计划

**目标：** 将 `D:\tanliniu\mumaren_finance\mumaren_finance_module\finance_module` 的财务领域能力直接移植并适配到华邦，同时与现有华邦旧财务完全隔离。

## 不可变边界

- 现有华邦路由已占用 `/api/v1/finance-center` 与 `/app/finance-center`。为不改变旧功能，新模块独占其子命名空间：API 为 `/api/v1/finance-center/mumaren/*`，页面为 `/app/finance-center/mumaren/*`；菜单显示为“财务利润 → 财务中心”。这两个路径仍统一属于要求的财务中心根路径，但不会匹配旧路由的端点或页面。
- 不得调用旧 `/api/v1/finance/*` 或任一旧 `/api/v1/finance-center/*` 写入口；不得导入 `frontend/src/views/finance/FormalLedger.vue` 或 `HistoricalFinance.vue`。
- 华邦仅提供认证、权限、数据库、路由注册、菜单和部署；不得注入旧财务模型或服务。
- 牧马人 `compat.py` 不直接使用；它将原项目 `app.*` 依赖映射进运行时，会破坏隔离。
- 新数据库对象仅使用 `finance_center_mumaren` schema；不得创建或使用 `fin_*`、`finance_*` 旧财务表。
- 业务凭证流程固定为“草稿 → 审核 → 人工过账”；禁止自动审核、自动过账和外部适配器自动制单。

## 映射

> **源模块核验结论（2026-07-31）：** `mumaren_finance_module` 提供的是财务
> API 结构、领域规则和宿主注入协议，并不包含可独立运行的 ORM、Alembic、前端、
> 月报服务实现或测试。不得直接加载其 `plugin.py` / `compat.py`；后者会劫持
> Python 的 `app.*` 模块缓存。华邦接入以源 API 的领域语义为准，在本模块独立
> schema 内实现真实模型、迁移和服务。`sales_monthly_report.py` 所需的 schemas/
> service 未随源模块交付，是后续完整月报的外部依赖，不能伪称已移植。

| 牧马人来源 | 华邦目标 | 处理 |
| --- | --- | --- |
| `finance_module/api/books.py` | `backend/app/api/v1/mumaren_finance_center.py`、`backend/app/services/mumaren_finance_center/` | 直接移植账套、科目、辅助核算领域语义，改为独立模型与华邦认证 |
| `finance_module/api/vouchers.py` | `backend/app/api/v1/mumaren_finance_center.py`、`backend/app/services/mumaren_finance_center/vouchers.py` | 移植凭证、审核、人工过账、账簿领域行为，禁止旧服务依赖 |
| `finance_module/api/reports*.py` | `backend/app/services/mumaren_finance_center/reports.py` | 使用独立账簿事实表计算报表 |
| `finance_module/api/history_archive.py` | `backend/app/services/mumaren_finance_center/history.py` | 金蝶单向导入新历史区，记录只读标记、来源键和导入批次 |
| `finance_module/api/*.py` 其余模块 | `backend/app/services/mumaren_finance_center/` | 逐个建立依赖与范围审计后移植；附件、自动制单、外部适配不启用 |
| 牧马人模型/服务注入 | `backend/app/models/mumaren_finance_center.py`、`backend/app/services/mumaren_finance_center/` | 新增独立 schema 与服务，不复用旧财务 |
| 牧马人服务器 `frontend/src/views/finance/` | `frontend/src/views/mumaren-finance-center/`、`frontend/src/api/mumarenFinanceCenter.ts` | 仅参考正式 Vue 页面的信息架构、表格、表单和布局；不得复制其旧 API、store、路由守卫或认证逻辑。源模块快照本身未附带该前端，故不能直接加载。 |

## 源 API 分批映射

| 源 API | 华邦新模块目标能力 | 波次 | 结论 |
| --- | --- | --- | --- |
| `books.py` | 账簿、科目、辅助核算、期初余额 | 1 | 移植领域语义；移除默认账套 `id=1` 和旧 `fin_*` SQL |
| `vouchers.py` | 凭证、分录、审核、人工过账、账簿 | 1 | 移植；状态固定草稿→审核→人工过账 |
| `reports.py` | 试算平衡、明细账、资产负债表、利润表 | 1 | 移植；只基于新 schema 已过账凭证 |
| `history_archive.py` | 金蝶历史归档与只读查询 | 1 | 移植；仅单向导入新历史区，保留来源键和批次 |
| `ar_ap.py` | 应收、应付、结算 | 2 | 移植到独立表；不得引用华邦旧业务表 |
| `business.py` | 出纳、资产、发票、工资 | 2 | 移植到独立表；附件和外部采集关闭 |
| `tax.py` | 税种、税务记录 | 2 | 移植到独立表 |
| `reports_extra.py` | 扩展报表 | 2 | 仅在基础账簿、科目、已过账凭证完成后迁移 |
| `compass.py` | 财务数据罗盘 | 3 | 仅接新财务数据；不引入牧马人门店/组织口径 |
| `daily_report.py`、`daily_ad_costs.py`、`sales_monthly_report.py`、`store_report_groups.py`、`daily_import.py`、`return_stats.py` | 日报、广告费、月报、店组、导入、退货统计 | 3 | 需先明确华邦本地来源；不得以牧马人服务或测试数据补猜 |
| `auto_entry.py` | 自动凭证 | 不迁移启用 | 按当前范围关闭；不注册可执行端点 |

## 实施波次

1. 新模型、迁移、认证权限依赖与最小路由壳；先测试前缀、401/403 和旧接口隔离。
2. 账簿、科目、凭证、期间、审计与历史只读导入；先测试迁移、幂等、只读标记。
3. 账簿/凭证/报表/历史前端页、菜单和中台权限接入；先测试路由与 API 边界。
4. 将牧马人扩展 API 按独立依赖逐一移植；附件、自动凭证、外部适配保持关闭。
5. 测试库迁移与历史导入、前端构建、浏览器验收；部署前单独审计生产条件。

## 每波验证

- 先新增失败测试，再做最小实现。
- 后端定向 pytest、迁移测试、前端类型检查和构建必须通过。
- 浏览器验收必须证明新页面不请求旧财务端点。

## 2026-08-01 运行与交接快照

以下为只读核验的当前状态，不等同于生产发布或生产验收结论。

| 项目 | 已核实状态 | 结论/限制 |
| --- | --- | --- |
| 本地功能分支 | `feature/huabang-full-finance-center` 的已提交基线为 `c82018b` | 该提交已存在于服务器的同名引用；当前本地工作树另有大量未提交的财务扩展改动，尚未完成范围审计、测试或提交，不能发布。 |
| 服务器生产工作树 | `/srv/huabang-ai-center` 当前在 `release/mumaren-finance-20260731`，HEAD 为备份提交 `f24938a`，且工作树存在未提交改动 | 生产工作树不等于功能分支；不得将其工作树状态描述为已部署独立财务中心。 |
| 生产服务 | `huabang-backend.service` 为 active，监听 `127.0.0.1:8000`，健康检查返回 HTTP 200 | 服务正常，但本次核验未执行生产财务功能验收，也未重启或部署。 |
| 8011 监听 | `127.0.0.1:8011` 当前由 `/home/xiaohu/worktrees/huabang-douyin-color-v31-rebased/frontend` 的 `vite preview` 占用 | 这不是牧马人财务测试 API。不得关闭、复用或把它作为财务验收服务；财务临时 API 必须在端口空闲后单独启动。 |
| 测试库与浏览器验收 | 先前报告称测试库为 `huabang_ai_finance_drill_20260729_r2`，并完成了单元/API 层验证 | 该报告需要在最终提交对应的测试工作树重新执行后才能作为当前证据。已登录浏览器端到端验收仍需独立、安全的测试账号；未完成前整体结论为测试环境 No-Go。 |

### 当前交接规则

1. 先冻结并审计未提交改动：区分独立财务中心的允许范围与无关文件；不得 `git add -A`。
2. 将允许范围内改动拆成可审查提交，在新的、明确指向测试库的工作树完成迁移、定向测试和构建。
3. 为测试库创建临时、最小权限的财务验收账号；密码只在验收进程内使用，结束后禁用，不得使用生产账号。
4. 仅在独立临时服务和测试库上完成浏览器点击流：凭证草稿→审核→人工过账、AR/AP 审核→结算、税务审核→缴税、历史金蝶只读。
5. 所有上述证据完成且通过单独生产发布评审后，才能讨论部署；本文件不授权生产发布、重启、迁移或写入生产库。
