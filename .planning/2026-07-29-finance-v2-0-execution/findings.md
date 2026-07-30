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

## 2026-07-30 连通性恢复与恢复副本前置复核

- SSH 已恢复。2026-07-30 01:03 UTC 生产主机 `hbreare-server` 在线，`huabang-backend.service` 为 `active`，`/health` 显示数据库、Redis 已连接；运行提交仍为 `bcdc1e9`。
- 本地当前工作树干净，后续期初工作流提交最高为 `dda0e6b`，包含未部署的数据库迁移 `016cfd3c1454`；尚不可将本地迁移或代码状态表述为生产完成。
- 恢复副本、备份可用性、生产数据库角色与远程分支仍需重新只读核实；在此之前禁止迁移与开写。
- 2026-07-30 首次读取计划时使用错误仓库根 `D:\huabang` 查找 `.planning`，未发生写入；已转入唯一目标工作树的活动计划。
- 数据库身份和授权尚未完成查询：首次探针在远程 Python 解析时因转义冲突失败，未连接数据库、未改变任何数据。
- 在当前 shell 加载的后端配置下，连接身份 `huabang` 对三个财务 schema 均无 `USAGE` 或 `CREATE`。这一事实与此前 `fin_app` 探针记录不一致，必须继续确认 systemd 使用的环境文件与实际应用运行时身份；未确认前不得以“已完成角色拆分”作为发布依据。
- 生产 systemd 的实际环境文件为 `/srv/huabang-ai-center/backend/.env`；对应数据库变量使用 `DB_*` 形式。应用连接可枚举 `fin_current`、`fin_history`、`fin_read` schema，但没有可见财务表，进一步确认当前运行身份没有表读取授权。
- 生产迁移 head 为 `1fdf4577d7d8`，本地 head 为 `016cfd3c1454`；远程功能分支目前只到 `6520e8f`，尚未包含本地 `8cf2b1a`、`dda0e6b`。任何部署必须先推送并在恢复副本验证。
- 2026-07-30 恢复副本创建尝试以全新数据库名 `huabang_finance_v2_restore_20260730` 被 PostgreSQL 明确拒绝：`permission denied to create database`。事前 `has_database_privilege(..., 'CREATE')` 只证明当前数据库内权限，不能推导 `CREATEDB` 角色属性；无恢复库、无生产表、无正式数据被创建或修改。
- 期初批次原先只有 `draft` 与 `locked` 服务操作，领域规则却要求 `validated` 才能锁定，导致任何草稿无法走到锁定。现已补齐显式验证命令及界面，并把最终锁定放在独立 `cutover_enabled` Gate 后；该 Gate 与 draft/review/post Gate 相互独立。
- 有效实施计划列为应创建的 API 契约和期初核对文档目前均不存在。这是文档交付缺口，不可据此推断接口、切换依据或人工核对说明已归档。
- 2026-07-30 再核实发现服务器仍保留 `huabang_ai_finance_drill_20260729_r2` 恢复副本：以 `fin_app` 可连接、含 `fin_current/fin_history/fin_read`、339 张已发布历史凭证和 0 当前账凭证。专用角色均存在，但生产环境文件只有 `FINANCE_DB_*`（运行 `fin_app`）凭据，未提供 `fin_migrator` 或 schema owner 的迁移连接；不能以 `fin_app` 执行 DDL。

## 2026-07-30 Phase 5 报表框架发现

- 原有 V2 仅有当前账试算表，且明确阻断资产负债表和利润表；没有模板、科目映射或快照表，更不存在可安全接通的正式报表出口。
- 本会话先补齐只读 report-readiness：它只能投影已发布模板版本和当前余额，缺映射、覆盖断档、资产负债不平或账簿阻断均返回原因，不能导出正式报表。
- 新迁移 `c82e5a1f9d70` 尚未在恢复副本验证；与未验证的 `016cfd3c1454` 一样，生产部署保持 No-Go。

## 2026-07-30 华邦中台来源候选只读核验

- 以运行账户 `huabang` 在生产 `huabang_ai` 做只读元数据和计数核验：`dwd.dwd_sales_detail` 有 466 条、唯一明细键 466 个，日期仅为 2026-06-14 至 2026-06-16；`dwd.dwd_return_detail` 有 1 条，日期为 2026-06-16。
- `dwd.dwd_finance_expense` 与 `dwd.dwd_finance_cash` 均为 0 行。销售、退货表没有收款/结算、税、法人、会计科目或已审核会计期间等完整记账事实。
- 因此本轮禁止把 DWD 汇总或经营明细直接映射成当前账凭证；可作为未来来源收件箱的只读快照候选，仍必须先补齐来源版本、法人/组织/账簿范围、收款结算与规则映射证据。

## 2026-07-30 增量迁移演练发现

- 生产实际 Alembic baseline 为 `1fdf4577d7d8`，本地 head 为 `e951b2d0a6c4`。从该 baseline 进行 `--sql` 预检可完整渲染三项待验证迁移；从数据库零版本进行离线渲染会触发既有迁移 `d5e6f7a8b9c0` 的运行时数据查询，不适合作为 V2 增量迁移校验。
- `rehearse_finance_v2_migrations.sh` 只对 `huabang_ai_finance_drill_*` 名称的恢复库执行，要求 baseline 精确匹配并在清理临时迁移口令后离开 recovery DB 于 head；生产库名无法通过参数校验。
- 当前 SSH 账户没有无交互 sudo，不能以应用账户执行 DDL，也不能安全代入任何管理员秘密。真实恢复库迁移仍需要受控 sudo/DBA 执行窗口。
