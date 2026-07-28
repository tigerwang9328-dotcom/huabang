# 华邦财务中心 V2.0 设计

> 文档状态：当前有效设计。

## 目标、边界与授权

V2.0 只交付可审计的会计内核和受控的当前账写入，不交付子账和专业模块。华邦本地工作树与已核实目标环境是唯一实施依据；牧马人财务目录只允许作为界面/业务边界参考，禁止引入其表、配置、服务、密钥或部署假设。金蝶 ODS/DWD 快照、百胜和钉钉事实表不被写回。

生产操作在每一 gate 达成后才执行；磁盘部署、服务重启和真实华邦数据验收分别记录，互不替代。

## 核心模型

```text
legal_entity → accounting_organization → accounting_book
                                          ├─ accounting_policy
                                          ├─ fiscal_calendar → fiscal_period
                                          ├─ chart_of_accounts → account_version
                                          ├─ dimension_definition → dimension_value
                                          └─ currency / exchange_rate
```

`account_version` 规定编码、名称、父级、层级、正常余额、末级/可记账、有效期、会计政策和版本。已使用科目不可删除或改码；期间在同一账簿不得重叠/重复，关闭后不可删除；科目父子不得成环、必须属于同一科目表版本，非末级科目禁止直接记账。`account_dimension_rule` 对每个可记账科目校验客户、供应商、部门、门店、员工、项目等维度的必填、禁止与组合规则。

任意维度组合存为 `dimension_set` 与排序的 `dimension_set_item`，由规范化维度项产生稳定哈希。`voucher_line`、`opening_balance_line` 与 `ledger_balance` 只引用 `dimension_set_id`，余额唯一键为 `(book_id, period_id, account_version_id, dimension_set_id, currency_code)`；不使用可无限扩展的 nullable 维度列，也不以未排序 JSON 作为唯一键。

金额保存原币、本位币、币种、汇率、汇率日期和来源；默认本位币是 CNY，但模型不假设唯一币种。金额使用 `NUMERIC(20,2)`，数量/单价使用 `NUMERIC(20,6)`，汇率使用 `NUMERIC(20,10)`，税率使用 `NUMERIC(12,8)`；会计政策规定单据级半向上舍入、舍入差异科目及报表展示位数。凭证分录借/贷均非负、不得同时大于零、汇率必须大于零。

## 当前账工作流与不变量

```text
draft → submitted → reviewing → approved → posted
           ↘ rejected ──reopen──→ draft
approved ──withdraw──→ draft
draft/submitted/reviewing/approved ──cancel──→ cancelled
```

`submitted → reviewing` 由具备审核范围的审核人以 `start_review` 明确领取。V2.0 固定为单人审核：一个凭证只能有一名活跃审核人，转交必须记录原因；多人会签不在 V2.0 实现范围，后续版本如启用必须另建 `review_instance/review_step/review_action` 模型。`cancelled` 是终态，需重新制单而非恢复。所有转换增加版本号；提交、拒绝、撤回、取消、过账和冲销都记录操作理由。凭证号码仅在人工过账时按“账簿 + 会计期间 + 凭证字”加锁分配；作废号码保留且不得重用。

| 当前状态 | 命令 | 目标状态 | 授权人 | 必填原因 |
| --- | --- | --- | --- | --- |
| draft | submit | submitted | 制单人 | 否 |
| submitted | start_review | reviewing | 审核人 | 否 |
| reviewing | approve | approved | 审核人 | 否 |
| reviewing | reject | rejected | 审核人 | 是 |
| rejected | reopen | draft | 制单人 | 是 |
| approved | withdraw | draft | 授权人员 | 是 |
| draft/submitted/reviewing/approved | cancel | cancelled | 制单人或授权人员 | 是 |
| approved | post | posted | 过账人 | 是 |
| posted | reverse | 原凭证仍为 posted + 新冲销凭证 posted | 反操作人员 | 是 |

过账失败不是凭证业务状态：余额事务失败时凭证仍保持 `approved`，失败详情写入 `fin_posting_attempt` 和 `fin_operation_event`。冲销不改变原凭证 `posted` 状态；原凭证记录 `reversal_status` 与 `reversal_voucher_id`，新的冲销凭证独立过账。已审核未过账凭证可因原因撤回到草稿；任何已过账凭证只能冲销或以调整凭证更正，永不编辑或删除。

制单、审核、过账默认职责分离；会计政策若允许审核人与过账人为同一人，必须显式配置并审计。每个写命令要求 `expected_version` 和原因，并以带版本条件的单行更新实现乐观并发。草稿可包含未完成或零金额行；提交前每行必须且只能有借/贷一边大于零，审核和过账前全凭证借贷相等且总额大于零；例外零金额业务类型须单独配置。余额只由过账/冲销事务更新，`ledger_balance` 是可重建读模型；提供 `rebuild_ledger_balance` 和 `verify_ledger_balance`。

锁定顺序固定为账簿、期间、凭证、余额；死锁与序列化失败有限重试。权限判定为“操作权限 + 账簿范围 + 组织范围 + 辅助维度范围 + 敏感字段范围”，不是单一全局权限码。

过账尝试采用独立审计事务：先写入 `fin_posting_attempt=running`，再运行可整体回滚的凭证/余额事务；成功后独立更新为 `success`，失败后在新的干净 session 中更新为 `failed`、错误码和脱敏上下文。失败不会把凭证从 `approved` 改为另一业务状态，也不会在已回滚 session 中写日志。

## 历史暂存、核对与发布

历史数据位于 `fin_history`，当前账位于 `fin_current`。角色严格分为 `finance_schema_owner`（仅对象所有权）、`finance_migrator`（仅 DDL/迁移）、`finance_app`（当前账受控 DML）、`finance_history_importer`（仅历史暂存/批次写入）和 `finance_readonly_auditor`（只读审计）；应用与导入角色均没有 DDL。`finance_history_importer` 仅能写 `fin_history.staging_*` 与批次控制表；`finance_app` 不得读取 `fin_history` 基础表，只能读取 `fin_read.history_*_view` 已发布视图。导入角色不可修改已发布业务实体，应用角色不可写历史 schema；历史业务表拒绝更新/删除。`import_batch`、检查点和校验结果是受控可更新的控制表，发布后只允许追加审计字段。部署中验证应用角色不是 owner 且没有 `BYPASSRLS`。`is_historical=true`、来源键、哈希和批次是审计标签，不是唯一安全屏障。

历史发布事实表为 `fin_history.accounting_book`、`account_version`、`voucher`、`voucher_line`、`balance_snapshot`、`source_link` 与可选的 `attachment_reference` 元数据。V2.0 仅保留来源附件引用、哈希或缺失状态的审计字段；不提供附件上传、下载、对象存储、版本控制或恶意文件扫描。发布短事务只将已验证 staging 批次转入这些不可变事实表（或将预先写入且不可变的分区标记为 published），随后把 `import_batch` 标为 `published`；`fin_read` 视图仅查询这些事实表的 published 批次，绝不直接查询 staging。

导入批次状态：

```text
created → loading → loaded → validating → validated → published
                 ↘ failed / conflicted / cancelled / superseded
```

仅 `published` 批次进入历史查询视图；加载中、失败或冲突数据对报表不可见。相同来源键与哈希记录 `already_imported`；同来源键不同哈希阻断并产生冲突报告；禁止覆盖历史来源。批次支持检查点和断点续传，但发布是短事务。

历史期末余额只作核对快照/性能读模型，不与凭证分录同时作为报表计算输入。历史报表和当前报表均由经批准的期初余额加已过账凭证分录计算；“含历史数据”遇范围重叠必须阻断或显式选择优先账簿并记录审计。

## 期初建账、结账与报表

当前账建账记录 `current_book_go_live_date`、`history_coverage_end_date`、`opening_balance_batch_id`、`opening_balance_status`、`opening_balance_approved_by` 和 `opening_balance_locked_at`。默认 `current_book_go_live_date = history_coverage_end_date + 1 天`；不连续时必须登记 `coverage_gap_start/end`、原因、受影响报表、批准人和 `formal_report_blocked=true`。期初批次包含 `opening_balance_line`、`opening_balance_dimension`、`opening_balance_reconciliation_item` 和 `opening_balance_approval`，每行保存账簿、期间、科目版本、维度集、币种、原币/本位币借贷、来源和核对状态。

Phase 4.5 建立 `provisional_opening_balance` 供只读验收使用；切换冻结后废弃预演批次，基于旧系统最终增量创建并批准 `final_opening_balance`。期初借贷相等、覆盖连续或已有获批断档、科目/维度余额核对一致后，财务负责人批准并锁定最终批次，才可开启 V2 制单。第一张正式凭证过账前允许废弃并重新创建最终期初；第一张正式凭证过账后及首次期间结账后，期初表永久只读，只能以当前开放期间调整凭证修正，不能再创建期初调整批次。

结账状态为 `open → closing → closed`，反结账状态为 `closed → reopening → open`。结账批次保存检查报告、损益结转凭证、重试与失败恢复记录；月结与年结分开建模，年结额外生成下一年度期初。结账前校验未审核/未过账/借贷不平为零、异常来源为零、余额重算通过、损益结转完成。重新打开期间需申请、理由、双人审批和审计，且不改变已过账凭证不可修改的规则。迟到来源单据不得自动重开期间，应进入异常队列，由财务选择当前期间调整凭证或受控反结账。V2.1/V2.2 启用子账后，子账-总账差异为零才可结账。

报表模板、项目/科目映射、公式、期间/年初数、舍入、快照、负责人确认与向科目/凭证/来源的穿透均版本化。映射或数据缺失时明确返回 `pending_mapping`、`pending_data`、`pending_gap`，不导出正式报表。

## 附件元数据、开关与监控

电子凭证预留原件、文件哈希、验签/验真状态、结构化载荷、归档状态、归档引用和入账信息文件。未验签/未验真仅显示真实状态。导出记录条件、字段、操作者、时间、水印和短期下载授权。

配置开关分为全局紧急停止、环境级、账簿级、来源系统级和角色试点范围：`finance_v2.read_enabled`、`draft_enabled`、`review_enabled`、`post_enabled`、`source_sync_enabled` 只能在其上级开关开启且角色/账簿范围获批准时生效。紧急停止可即时关闭当前写入与自动草稿。关键写命令必须携带 `command_id`、`request_id` 和 `idempotency_key`，并以数据库唯一约束防止浏览器/网关重试重复执行。监控过账失败、借贷不平阻断、历史冲突、收件箱积压、异常队列、锁等待/死锁、结账失败、导出异常、API 5xx、当日凭证与余额差异；V2.1 起增加子账-总账差异。每项监控具有阈值、负责人、通知路由、日志脱敏与关闭条件。

## V2.0 来源边界

V2.0 只实现 `source_inbox`、映射/过账规则版本、异常队列、适配器接口和生产数据的只读 `dry-run/preview`。百胜与钉钉适配器不得在 V2.0 生产环境生成或过账正式草稿；任何有限来源试点属于 V2.1，必须逐来源批准，说明未来子账需求、总账—子账关联键、补建历史策略和回滚方式。

## API、路由与切换契约

唯一后端前缀为 `/api/v1/finance-center`，唯一前端前缀为 `/app/finance-center`；根路由在 `backend/app/api/v1/router.py` 注册，前端路由在 `frontend/src/router/index.ts` 注册，菜单单一来源为 `frontend/src/config/financeCenterModules.ts`。V2 只读验收阶段，旧 `/api/v1/finance/*` 与旧页面保持原有正式写入行为，V2 不代理旧写命令、不创建草稿也不改正式账。切换完成后，API 契约表将旧查询映射为 V2 只读代理或废弃提示，旧制单映射为 V2 制单或 410，旧审核/过账永久为 410。

默认在会计期间边界切换：旧系统完成当期结账 → 取得期末余额 → 生成/批准 V2 下一期间最终期初 → 下一期间第一天启用 V2。必须月中切换时，`import_finance_cutover_delta` 导入本期起始日至切换日的旧凭证为 V2 当前账迁移凭证，保留原编号、日期、科目、维度和来源；逐凭证/逐余额核对并防止重复记账。

切换顺序为：旧系统正常写入 → V2 只读验收 → V2 凭证工作台/权限验收 → 短时冻结旧系统全部写入 → 提取/导入/核对最终增量并批准最终期初 → 开启 V2 制单 → 永久关闭或转接旧制单/审核/过账 → 日对账后开启 V2 审核 → 再开启 V2 人工过账。旧系统在只读验收阶段始终是唯一正式写账系统；冻结窗口期间两侧写入均关闭；不得出现未计划的无写入系统停摆。

## 性能、审计与附件恢复 Gate

`operation_event` 只能追加，应用角色不可更新/删除；事件保存旧值、新值、原因、命令 ID 和保留期限，高风险操作使用哈希链或外部不可变日志。生产开写前须在生产形态数据上验收余额表百万级分录响应、明细分页、单凭证过账 P95、月结耗时、历史导入吞吐、报表并发、锁等待/死锁上限及大附件/批量导出资源限制。

附件、电子凭证原件和归档文件的上传、对象存储、版本控制、恶意文件扫描和恢复演练不属于 V2.0。本版只要求导入或人工登记的附件引用元数据不得冒充文件已归档；待后续附件专项立项后再定义存储、扫描和恢复门槛。

## 版本回退与灾难恢复

超过应用发布回退点后，普通发布故障只允许前向修复，不能因应用错误盲目恢复迁移前数据库。数据库物理损坏、存储故障、大范围误删或安全事件仍按已验证的 PITR/备份恢复流程处理，并对 RPO 范围内缺失交易进行重放、补录和财务核对。
