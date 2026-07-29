# V2.0 发现记录

## 有效依据

- 唯一执行文档：`docs/finance/v2.0/roadmap.md`、`design.md`、`implementation-plan.md`。
- 当前实施工作树：`D:\huabang\worktrees\kingdee-finance-local`。
- 生产运行目录：`/srv/huabang-ai-center`；2026-07-29 最近代码运行提交为 `367bbee`。

## 已核实状态（本会话前后）

- 已生产发布历史金蝶只读数据：339 张凭证、4,596 条分录；当前账 `fin_current` 仍无业务凭证。
- 已实现并发布中台 Finance V2 权限、历史只读查询、账簿/期间/科目查询、试算表、结账检查、特性 Gate、监控策略、凭证状态命令与凭证详情/草稿编辑。
- 所有当前账写 Gate 保持关闭；生产写入行为没有在本次发布中执行。
- 生产本机逻辑备份和 PITR 技术演练有证据，但无异机/异存储副本，不能覆盖主机故障。

## 计划审计重点

- 不能以旧 `.planning/2026-07-20-*` 中的 `fin` schema 计划替代现在的 `fin_current`/`fin_history` V2.0 计划。
- 需首先核实基础报表、期初余额、冲销/调整、来源 preview、遗留契约和浏览器验收的真实覆盖，不从文档目录或接口名称推断已完成。

## Phase 4.5 当前发现

- `fin_current.opening_balance_batch` 与 `opening_balance_line` 已有模型、迁移和纯领域校验；领域测试覆盖平衡、批准与覆盖连续性。
- 本会话新增 `opening_balance_service.py`，并把最终、已锁定、覆盖连续且日期无断层的期初余额接入所有当前账写 Gate 与只读 readiness。服务不创建或伪造期初数据。
- 仍缺受控的期初余额制备/校验/锁定工作流、数据库级锁定不变量和已批准最终期初数据；因此正式开写仍为 No-Go。
