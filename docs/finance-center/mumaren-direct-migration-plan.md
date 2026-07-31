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
| 牧马人无前端资产 | `frontend/src/views/mumaren-finance-center/`、`frontend/src/api/mumarenFinanceCenter.ts` | 使用华邦 Vue 路由、菜单、认证壳实现页面 |

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
