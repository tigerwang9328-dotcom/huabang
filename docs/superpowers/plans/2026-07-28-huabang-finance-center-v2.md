# 华邦财务中心 V2.1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重建完整华邦财务中心，将金蝶历史数据作为带标记的只读历史账导入，并让华邦业务数据仅通过草稿、审核、人工过账进入当前正式账。

**Architecture:** 新财务中心以 `fin` schema 和 `/api/v1/finance-center` 为唯一契约。金蝶历史导入与当期账分层；百胜、钉钉适配器只生产来源可追溯的草稿；过账服务是唯一能更新总账余额与法定报表输入的入口。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL、pytest、Vue 3、TypeScript、Element Plus、Vite、Playwright。

## 全局约束

- 金蝶 ODS/DWD 快照、`dwd_finance_expense`、`dwd_finance_cash`、百胜与钉钉事实表不可被财务中心写入。
- 历史金蝶数据写入 `fin` 后必须永久带 `is_historical=true` 和完整来源链路；默认只读。
- 当前账务状态只能为草稿、审核、人工过账；自动化只创建草稿。
- 金额使用 `Decimal`/数据库 `NUMERIC`，已过账分录借贷单边非负且每张凭证借贷平衡。
- 每个迁移、导入、发布前后均需保留备份和机器可读核对报告；生产迁移后 Alembic 必须只有一个 head。

---

### Task 1: 现状基线与替换边界

**Files:**
- Modify: `docs/finance/finance-center-baseline.md`
- Test: `backend/tests/test_finance_center_api.py`

**Interfaces:** 记录当前 `finance_center.py`、`finance_center_service.py`、`kingdee_finance.py` 和 `financeCenterModules.ts` 的实际契约，列出必须保留的旧 `/api/v1/finance/*` 与 `/app/fin/*` 兼容入口。

- [ ] 写入会失败的接口契约测试，断言新入口为 `/api/v1/finance-center/*`，旧 `/api/v1/finance/*` 不被删除。
- [ ] 运行 `cd backend; pytest tests/test_finance_center_api.py -q`，确认失败原因是新契约尚未完整提供。
- [ ] 记录当前财务路由、权限码、模型、迁移 head、历史导入基线和生产服务部署方式；每项注明“本地证据/生产证据/待核验”。
- [ ] 将旧拆分页标记为兼容入口或待替换调用方，不将其复制为新模块实现。
- [ ] 再运行契约测试，确认基线测试可执行且失败信息准确。

### Task 2: 财务核心模型与历史标记迁移

**Files:**
- Modify: `backend/app/models/kingdee_finance.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/6f3d8c2a1b40_merge_finance_center_v2_heads.py`
- Create: `backend/alembic/versions/7a4e9d2c1b60_finance_center_v2_history_marker.py`
- Test: `backend/tests/test_finance_center_models.py`

**Interfaces:** 所有 `fin` 历史可导入实体暴露 `is_historical: bool`、`origin_kind: str`、`source_system: str`、`source_database: str | None`、`source_pk: str`、`import_batch_id: str` 和 `source_hash: str`；来源唯一键覆盖账套与来源身份。

- [ ] 编写失败测试，创建两条相同历史来源记录并断言唯一约束拒绝重复；创建当前记录并断言不能带 `kingdee_history` 标记。
- [ ] 运行 `cd backend; pytest tests/test_finance_center_models.py -q`，确认因字段/约束缺失而失败。
- [ ] 先以 `6f3d8c2a1b40` 合并当前三个 head：`299f6a7b8c92`、`2a0f6a7b8c93`、`6c1e4a7d2f09`；该合并 revision 不执行 schema 变更。
- [ ] 在 `7a4e9d2c1b60` 迁移中新增不可空历史标记和来源字段、来源唯一索引、按 `is_historical` 的查询索引；对已存在导入记录按可验证来源回填，无法回填的记录迁移失败。
- [ ] 注册模型后执行 `cd backend; alembic heads`，确认仅一个 head。
- [ ] 重跑模型测试，确认通过。

### Task 3: 历史数据导入、幂等与核对

**Files:**
- Modify: `backend/app/services/finance_center_service.py`
- Modify: `backend/scripts/import_kingdee_finance.py`
- Create: `backend/scripts/verify_finance_history_import.py`
- Test: `backend/tests/test_import_kingdee_finance.py`
- Test: `backend/tests/test_finance_history_marker.py`

**Interfaces:** 导入命令支持 `--dry-run`、`--apply`、`--batch-id`；验证命令输出 JSON，包含账套、科目、凭证、分录、余额、借贷合计、来源链接、重复数和差异数。

- [ ] 编写失败测试：首次导入产生历史标记；第二次同源导入不新增行；源哈希不同时返回阻断差异；历史凭证拒绝更新、审核、过账和删除。
- [ ] 运行两个导入测试，确认失败原因是历史隔离行为尚未实现。
- [ ] 实现以来源键和哈希为边界的 upsert；导入账套、期间、科目、凭证、分录、余额和来源链接时写入同一批次审计。
- [ ] 实现逐账套与总计核对；将导入批次、失败明细和原始来源引用写入报告，任何金额/借贷差异返回非零退出码。
- [ ] 在测试库连续运行两次 `python scripts/import_kingdee_finance.py --apply --batch-id test-history-v2`，再运行验证脚本；断言行数与金额不变。

### Task 4: 当前账凭证状态机、余额与期间锁

**Files:**
- Modify: `backend/app/services/finance_center_service.py`
- Modify: `backend/app/api/v1/finance_center.py`
- Test: `backend/tests/test_finance_center_service.py`
- Test: `backend/tests/test_finance_center_api.py`

**Interfaces:** `create_draft`、`update_draft`、`review_voucher`、`post_voucher`、`reverse_voucher` 和 `close_period`；所有写命令接收 `expected_version` 与 `reason`，历史凭证统一返回 `FIN_HISTORICAL_READ_ONLY`。

- [ ] 编写失败测试：未平衡草稿不能审核；审核后才能过账；过账后余额变化一次；版本过期返回 409；历史标记凭证的写命令返回只读错误。
- [ ] 运行服务与 API 测试，确认失败属于状态机/权限缺失。
- [ ] 使用数据库事务和期间行锁实现状态流转；过账服务是唯一更新余额的路径；每个状态变化记录前后快照、操作者与原因。
- [ ] 运行测试并检查没有 `float` 参与金额计算。

### Task 5: 华邦来源适配器与自动草稿

**Files:**
- Create: `backend/app/services/finance_center_adapters.py`
- Modify: `backend/app/services/finance_center_service.py`
- Modify: `backend/app/api/v1/finance_center.py`
- Test: `backend/tests/test_finance_auto_entry.py`

**Interfaces:** `SourceDocument` 包含 `source_system`、`source_pk`、`book_id`、`business_date`、`amount`、`tax_amount`、`organization`、`counterparty`、`attachments`、`source_hash`；适配器为百胜和钉钉生成它，规则服务只返回草稿或异常队列项。

- [ ] 编写失败测试：销售、退货、报销和付款各生成一张平衡草稿；缺科目或组织映射写异常；重复来源不生成第二张有效草稿；草稿不会改变余额。
- [ ] 运行 `cd backend; pytest tests/test_finance_auto_entry.py -q`，确认失败原因是适配器或规则不存在。
- [ ] 读取华邦实际字段并实现受控 SQL/服务适配，不使用牧马人表名或配置；保留原单号和来源哈希。
- [ ] 对每条生成的草稿调用同一凭证服务；禁止适配器调用审核或过账接口。
- [ ] 重跑测试，确认仅人工过账后才影响账簿。

### Task 6: 业务域 API 与权限审计

**Files:**
- Modify: `backend/app/api/v1/finance_center.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/scripts/seed_module_permissions.py`
- Test: `backend/tests/test_finance_center_permissions.py`
- Test: `backend/tests/test_finance_center_api.py`

**Interfaces:** `/api/v1/finance-center/{books,accounts,vouchers,ledgers,reports,receivables,payables,cash,assets,invoices,payroll,taxes,periods,settings,audit}`；权限为 `finance:center:view`、`finance:voucher:write`、`finance:voucher:post`、`finance:period:close`、`finance:settings:write`、`finance:sensitive:view`、`finance:export`。

- [ ] 编写失败测试：非财务用户 403；老板可读/导出但不可写；财务制单者不可越权过账；历史查询必须返回历史标记。
- [ ] 运行权限和 API 测试，确认失败原因是端点或权限断言尚未落实。
- [ ] 按华邦统一响应格式实现分页、筛选、错误码与审计；旧 API 保留兼容，不重定向到未实现端点。
- [ ] 执行权限种子脚本于测试库并重跑测试。

### Task 7: 全量前端财务中心与导航

**Files:**
- Modify: `frontend/src/config/financeCenterModules.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Create: `frontend/src/api/financeCenter.ts`
- Create: `frontend/src/views/finance-center/FinanceDashboard.vue`
- Create: `frontend/src/views/finance-center/FinanceWorkspace.vue`
- Create: `frontend/src/views/finance-center/HistoryDataBadge.vue`
- Test: `frontend/tests/finance-center.spec.ts`

**Interfaces:** 所有财务中心子页经 `/app/finance-center/*` 提供；“财务利润 → 财务中心”为唯一导航来源；前端 API 只调用 `/api/v1/finance-center/*`。

- [ ] 编写失败的路由/菜单测试：财务中心在财务利润下；旧入口仍存在；每个新子页有真实 API 请求；历史行显示“历史数据”；默认报表范围为当前账。
- [ ] 运行 `cd frontend; npm run test -- finance-center`，确认失败原因是路由/页面/组件缺失。
- [ ] 实现共享账套、期间和数据范围工具栏；实现凭证、账簿、报表、往来、出纳、资产、发票、工资、税务、结账、设置页面，空数据状态须说明缺失原因。
- [ ] 页面按权限隐藏或禁用写操作；过账与反操作显示原因填写和二次确认；历史记录不能出现可执行写按钮。
- [ ] 运行 `npm run type-check` 和 `npm run build`，确认均退出 0。

### Task 8: 试迁移、发布、数据接入与生产验收

**Files:**
- Create: `docs/finance/finance-center-v2-runbook.md`
- Create: `docs/finance/finance-center-v2-acceptance.md`
- Create: `deploy/release_finance_center_v2.ps1`

**Interfaces:** 发布脚本须先备份、迁移、历史导入核对、构建、原子发布、受控重启和生产验证；每一步输出可保存日志和明确失败码。

- [ ] 在测试数据库备份恢复副本上运行 Alembic、历史导入两次、来源适配预览和完整后端测试；保存 JSON 核对报告。
- [ ] 运行前端类型检查、构建与浏览器测试，覆盖登录、财务中心菜单、历史标记、草稿、审核、人工过账、账簿穿透和权限拒绝。
- [ ] 生产前执行并验证 PostgreSQL 全量可恢复备份，确认 Alembic 单 head、发布负责人和回滚负责人。
- [ ] 按已验证部署脚本发布；迁移或导入差异非零时停止，不重启服务。
- [ ] 迁移、历史核对、构建切换成功后重启已授权后端服务，检查健康端点、关键 API、浏览器路径、日志和历史标记。
- [ ] 直接接入华邦数据前先运行适配预览；由财务人员核对草稿后，再开启草稿生成；任何自动审核/过账信号为 No-Go。
- [ ] 保存发布、回滚、备份与验收证据；发生 5xx、金额不符、越权或历史数据被写入时立即回滚应用并按迁移前备份恢复。

## 完成门槛

- [ ] 新模块不复用旧拆分实现作为后端事实来源。
- [ ] 历史金蝶数据已写入新模块、带可见历史标记、重复导入幂等且不可被当前流程修改。
- [ ] 所有当前写入都遵循草稿、审核、人工过账；适配器只生成草稿。
- [ ] 全部业务域有真实 API 和页面，缺数据时清楚标识而非模拟成功。
- [ ] 本地、试迁移、部署、生产重启、真实华邦数据接入与人工验收分别保存证据并分别报告。

## V2.1 实施顺序修订（本节替代原 Task 1—8 的执行顺序）

原计划中的“完整业务域 API”和“全量前端”不再作为单个任务执行。以下阶段按顺序推进；每个阶段的 Go 门槛未满足，不得进入下一阶段，更不得上线开写。

### Phase 0: 证据、口径与发布基线

**Files:**
- Create: `docs/finance/v2-0-evidence-register.md`
- Create: `docs/finance/v2-0-accounting-policy-signoff.md`
- Create: `docs/finance/v2-0-release-baseline.md`

- [ ] 核对本地与生产仓库提交、数据库版本、全部 Alembic heads、Python/Node 运行时、systemd 或容器编排、当前发布锁方式和数据库角色；将未验证项标为待确认。
- [ ] 由财务负责人确认法人主体、核算组织、账套、法定账/管理账范围、会计政策、科目表、辅助核算、期间、期初余额、币种和报表口径；未签字不得进入数据库建模。
- [ ] 产出金蝶源快照清单、哈希、账套/期间/科目/凭证/分录/余额基线，并记录已知缺口。
- [ ] 运行 `git status --short`、迁移 head 检查和现有财务测试；将实际输出写入基线，不用计划中的假设替代事实。

### Phase 1: 迁移图与数据库角色先决条件

**Files:**
- Create: `backend/alembic/versions/6f3d8c2a1b40_merge_finance_center_v2_heads.py`
- Create: `backend/scripts/verify_finance_database_roles.py`
- Test: `backend/tests/test_finance_database_roles.py`

- [ ] 写失败测试：应用数据库角色无 `fin_history` 的插入、更新、删除权限；历史导入角色无 `fin_current` 写权限；表所有者和应用角色均不具备 `BYPASSRLS`。
- [ ] 在实施当天重新读取所有 heads；仅当仍为 `299f6a7b8c92`、`2a0f6a7b8c93`、`6c1e4a7d2f09` 时，创建该固定 merge revision；否则用当日实际 heads 生成新的合并 revision 并更新本计划与证据登记册。
- [ ] 运行 `alembic heads`，确认 merge 后恰有一个 head；多 head 为 No-Go。
- [ ] 用只读角色检查实际 PostgreSQL 角色、owner、`BYPASSRLS`、schema grants、PITR/备份能力；缺任一生产权限隔离条件则停止在测试环境。

### Phase 2: V2.0 会计内核模型（Expand）

**Files:**
- Create: `backend/app/models/finance_core_v2.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/7a4e9d2c1b60_finance_core_v2_expand.py`
- Test: `backend/tests/test_finance_core_v2_models.py`

- [ ] 先写失败测试，覆盖法人/组织/账套/账簿/政策/期间日历、科目版本、辅助维度规则、币种、汇率、账簿数据域、历史来源字段和复合外键。
- [ ] 迁移只创建 `fin_current`、`fin_history` 和可空兼容结构；不在此阶段增加不可空字段、全表回填或阻塞索引。
- [ ] 规定科目不可变编码、有效期、正常余额、末级/可记账规则和辅助维度组合验证；金额用 `NUMERIC`，默认 CNY 但模型不假设唯一币种。
- [ ] 运行模型测试和测试库 `alembic upgrade head`；保存 DDL 与 head 输出。

### Phase 3: 凭证工作流、账簿不变量与防并发

**Files:**
- Create: `backend/app/services/finance_v2/voucher_workflow.py`
- Create: `backend/app/services/finance_v2/ledger_service.py`
- Create: `backend/app/services/finance_v2/period_closing_service.py`
- Test: `backend/tests/test_finance_v2_voucher_workflow.py`
- Test: `backend/tests/test_finance_v2_concurrency.py`

- [ ] 写失败测试，覆盖 `draft/submitted/reviewing/approved/posted/rejected/cancelled/posting_failed/reversed`、制单审核分离、连续凭证号、借贷平衡、冲销/更正、关闭期间限制与不允许修改已过账凭证。
- [ ] 以 `WHERE id=:id AND version=:expected_version` 实现所有单记录写入；影响行数非 1 返回 409，禁止绕过服务的批量更新。
- [ ] 固定锁序为账簿、期间、凭证、余额，并为死锁/序列化失败实现有上限的重试；测试同凭证过账、同来源制单、结账与过账、冲销与结账并发。
- [ ] 只让 `post`/`reverse` 事务更新余额；每一步写不可篡改操作事件、版本快照和原因。

### Phase 4: 历史账隔离与分批导入（Migrate）

**Files:**
- Create: `backend/app/services/finance_v2/history_import_service.py`
- Create: `backend/alembic/versions/7b5f0e3d2c61_finance_history_guards.py`
- Create: `backend/scripts/import_finance_history_v2.py`
- Create: `backend/scripts/verify_finance_history_v2.py`
- Test: `backend/tests/test_finance_v2_history_import.py`

- [ ] 写失败测试，证明应用角色不能改历史表、触发器拒绝更新/删除、相同来源键和哈希只产生 `already_imported`、同来源键异哈希阻断、历史记录不接受任何当前账命令。
- [ ] 以导入批次分批写入历史 schema；禁止 `ON CONFLICT DO UPDATE` 覆盖来源证据。
- [ ] 每个批次逐账套、年度、期间、科目、辅助维度、凭证、分录、期初/借贷/期末、原币/本位币、来源单据和附件核对；报告不可通过时非零退出。
- [ ] 在恢复副本连续执行两次导入，比较全量快照和哈希；只读前端验收可见“历史数据”及默认不混算。

### Phase 5: 总账、基础报表、附件与只读发布

**Files:**
- Create: `backend/app/api/v1/finance_v2.py`
- Create: `frontend/src/api/financeV2.ts`
- Create: `frontend/src/views/finance-center/V2CoreWorkspace.vue`
- Create: `frontend/src/views/finance-center/HistoryDataBadge.vue`
- Create: `deploy/release_finance_center_v2.sh`
- Create: `deploy/release_finance_center_v2.ps1`
- Create: `deploy/verify_finance_center_v2.py`
- Test: `backend/tests/test_finance_v2_reports.py`
- Test: `frontend/tests/finance-v2-core.spec.ts`

- [ ] 写失败测试：总账、明细账、余额表、资产负债表和利润表只使用已过账当前账或明确选择的历史范围；未确认映射不可导出正式报表；导出记录水印与下载时效。
- [ ] 接入历史只读查询与当前账读模型；在“财务利润 → 财务中心”下仅开放 V2.0 页，其余域显示未启用。
- [ ] 构建电子附件的接收、哈希、归档状态和权限骨架；未验签/未验真必须如实显示，不能伪称完成验证。
- [ ] 脚本以 Linux `sh` 为生产执行入口，PowerShell 仅通过 SSH 调用它；二者使用发布锁、显式环境注入、原子前端切换和可保存日志。
- [ ] 生产先只读发布：备份恢复演练、兼容迁移、导入核对、API/权限/浏览器验收全部通过后才到下一阶段。

### Phase 6: 受控开启当前账写入与华邦适配器

**Files:**
- Create: `backend/app/services/finance_v2/source_inbox.py`
- Create: `backend/app/services/finance_v2/baison_adapter.py`
- Create: `backend/app/services/finance_v2/dingtalk_adapter.py`
- Test: `backend/tests/test_finance_v2_source_inbox.py`
- Create: `docs/finance/v2-0-write-enable-runbook.md`

- [ ] 先写失败测试：来源单据版本、哈希和幂等键唯一；缺映射进入异常队列；百胜/钉钉只产生草稿且不改变余额。
- [ ] 先启用制单，再启用审核，最后启用人工过账；每个开关间隔至少完成当日核对，任何异常回退到上一只读或草稿阶段。
- [ ] 在回退点前冻结写入；回退点后只允许前向修复。若已产生真实写入，恢复旧备份前必须导出并演练重放新写入。
- [ ] 首周每日输出来源单据、草稿、审核、过账、余额和异常队列对账；未通过不得扩大范围。

### Phase 7: V2.1 子账逐域实施

**Files:**
- Create: `docs/finance/v2-1-subledger-gates.md`

- [ ] 按“费用/付款与发票 → 应收 → 应付 → 出纳/银行对账”顺序，每个子域独立建模、迁移、来源接入、子账与总账对账、页面、权限、性能及生产验收。
- [ ] 每个子域完成前，总账结账检查只显示该域为未启用；启用后将其差异为零纳入结账前置条件。
- [ ] 不得把 CRUD、空表或模拟数据视为子域完成。

### Phase 8: V2.2 专业域逐项实施

**Files:**
- Create: `docs/finance/v2-2-specialized-domain-gates.md`

- [ ] 按“固定资产/折旧 → 工资 → 税务 → 现金流量表自动分配 → 管理会计/预算/合并报表”顺序单独立项。
- [ ] 每项必须补齐数据来源、会计政策、子账-总账对账、敏感数据控制、结账依赖和回滚策略后才可实施。

## 修订后的完成门槛

- [ ] V2.0 仅在会计内核、历史隔离、基础账簿报表、只读发布和受控开写全部有证据时完成。
- [ ] V2.1/V2.2 模块不因存在页面、接口或表而视为已完成；必须按各自 gate 通过。
- [ ] 发布恢复策略区分“写入冻结可回退”和“已开写仅前向修复”，并验证 RPO/RTO/备份恢复。
