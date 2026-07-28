# 华邦财务中心 V2.0 设计

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

`account_version` 规定编码、名称、父级、层级、正常余额、末级/可记账、有效期、会计政策和版本。已使用科目不可删除或改码。`account_dimension_rule` 对每个可记账科目校验客户、供应商、部门、门店、员工、项目等维度的必填、禁止与组合规则。

金额保存原币、本位币、币种、汇率、汇率日期和来源；默认本位币是 CNY，但模型不假设唯一币种。凭证分录借/贷均非负、不得同时大于零、汇率必须大于零。

## 当前账工作流与不变量

```text
draft → submitted → reviewing → approved → posted
          ↘ rejected → draft
draft/submitted/reviewing/approved → cancelled
```

过账失败不是凭证业务状态：余额事务失败时凭证仍保持 `approved`，失败详情写入 `fin_posting_attempt` 和 `fin_operation_event`。冲销不改变原凭证 `posted` 状态；原凭证记录 `reversal_status` 与 `reversal_voucher_id`，新的冲销凭证独立过账。已审核未过账凭证可因原因撤回到草稿；任何已过账凭证只能冲销或以调整凭证更正，永不编辑或删除。

制单、审核、过账默认职责分离；会计政策若允许审核人与过账人为同一人，必须显式配置并审计。每个写命令要求 `expected_version` 和原因，并以带版本条件的单行更新实现乐观并发。余额只由过账/冲销事务更新，`ledger_balance` 是可重建读模型；提供 `rebuild_ledger_balance` 和 `verify_ledger_balance`。

锁定顺序固定为账簿、期间、凭证、余额；死锁与序列化失败有限重试。权限判定为“操作权限 + 账簿范围 + 组织范围 + 辅助维度范围 + 敏感字段范围”，不是单一全局权限码。

## 历史暂存、核对与发布

历史数据位于 `fin_history`，当前账位于 `fin_current`。`finance_history_importer` 是唯一能写历史 schema 的角色；应用角色仅可读取，历史表拒绝更新/删除；部署中验证应用角色不是 owner 且没有 `BYPASSRLS`。`is_historical=true`、来源键、哈希和批次是审计标签，不是唯一安全屏障。

导入批次状态：

```text
created → loading → loaded → validating → validated → published
                 ↘ failed / conflicted / cancelled / superseded
```

仅 `published` 批次进入历史查询视图；加载中、失败或冲突数据对报表不可见。相同来源键与哈希记录 `already_imported`；同来源键不同哈希阻断并产生冲突报告；禁止覆盖历史来源。批次支持检查点和断点续传，但发布是短事务。

历史期末余额只作核对快照/性能读模型，不与凭证分录同时作为报表计算输入。历史报表和当前报表均由经批准的期初余额加已过账凭证分录计算；“含历史数据”遇范围重叠必须阻断或显式选择优先账簿。

## 期初建账、结账与报表

当前账建账记录 `current_book_go_live_date`、`history_coverage_end_date`、`opening_balance_batch_id`、`opening_balance_status`、`opening_balance_approved_by` 和 `opening_balance_locked_at`。期初借贷相等、起始日不与历史覆盖重叠、科目/维度余额核对一致后，财务负责人批准并锁定。后续修改只能创建新的期初调整批次，不能直接改余额。

结账前校验未审核/未过账/借贷不平为零、异常来源为零、余额重算通过、损益结转完成。重新打开期间需申请、理由、双人审批和审计，且不改变已过账凭证不可修改的规则。V2.1/V2.2 启用子账后，子账-总账差异为零才可结账。

报表模板、项目/科目映射、公式、期间/年初数、舍入、快照、负责人确认与向科目/凭证/来源的穿透均版本化。映射或数据缺失时明确返回 `pending_mapping`、`pending_data`、`pending_gap`，不导出正式报表。

## 电子附件、开关与监控

电子凭证预留原件、文件哈希、验签/验真状态、结构化载荷、归档状态、归档引用和入账信息文件。未验签/未验真仅显示真实状态。导出记录条件、字段、操作者、时间、水印和短期下载授权。

配置开关为 `finance_v2.read_enabled`、`draft_enabled`、`review_enabled`、`post_enabled`、`source_sync_enabled`，并有可即时关闭写入与自动草稿的紧急停止开关。监控过账失败、借贷不平阻断、历史冲突、收件箱积压、异常队列、锁等待/死锁、结账失败、导出异常、API 5xx、当日凭证与余额差异；V2.1 起增加子账-总账差异。
