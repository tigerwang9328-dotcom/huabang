# V2.0 进度记录

## 2026-07-29 Phase 1

- **Status:** in_progress
- 建立新的 V2.0 执行台账，替代与已归档 `fin` 方案绑定的旧规划文件。
- 已知本会话发布：`367bbee`（生产代码）；`44ef994`（发布证据文档，已推送但不需要运行时部署）。
- 下一动作：基于当前工作树审计有效实施计划各阶段的真实代码和测试覆盖。
- 审计确认 Phase 4.5 的期初余额只有模型/迁移/纯领域测试，尚无持久化服务或 API，且当前草稿 Gate 未强制最终锁定期初；下一步以此作为测试先行缺口。

## 错误记录

| 时间 | 错误 | 处理 |
| --- | --- | --- |
| 2026-07-29 | 旧 `.planning` 指向早期 `fin` 方案，与当前有效 `fin_current`/`fin_history` V2.0 设计冲突 | 新建独立 V2.0 计划，不复用旧计划结论 |
# 2026-07-29 Phase 4.5 运行时边界开始

- 已确认模型和纯领域函数存在，但 API 写 Gate 没有查询 `opening_balance_batch`；若日后单独打开 Gate，当前账命令可能绕过最终期初要求。
- 本轮先补该缺口的失败测试和服务层绑定；生产 Gate 维持关闭，不录入虚构期初数据。
- 已完成最小运行时绑定并通过 124 项 V2/数据库角色/历史导入回归：所有 Gate 打开时仍须存在同账簿、同启用日的最终锁定期初余额；历史截止日必须正好是启用日前一日。未部署，待最小权限和生产读路径复核。

## 2026-07-29 Phase 4.5 运行时边界发布

- 已推送并发布 `bcdc1e9` 至 `/srv/huabang-ai-center`；后端于 15:06:38 UTC 重启，`/health` 返回数据库和 Redis 已连接。
- 生产 `fin_app` 只读探针确认可读取 `fin_current.opening_balance_batch`；未运行迁移、未更改任何 V2 Gate、未写入任何账务/期初数据。
- 浏览器工具连接到另一枚抖音 Chrome 标签，不能证明华邦中台已登录用户验收；该 Gate 保持未完成，不将 401 未授权路由探针冒充为业务验收。

## 2026-07-29 Phase 4.5 预演期初制备开始

- 已以失败测试驱动实现 `create_batch`：创建预演/最终期初草稿时写入来源行、命令幂等记录和审计事件，但不改变账簿启用日、不锁定期初、也不改变 V2 写 Gate。
- 完整的 validate/lock/discard 重建语义需要 `version`、审批、核对项、获批断档和锁定触发器；迁移 revision 已按当前 head 生成过用于核实图，但尚未提交或执行，待完整工作流与恢复副本用例一起落盘。

## 2026-07-29 Phase 4.5 迁移控制层

- 新 revision `016cfd3c1454` 基于当日真实 head 生成，包含批次版本、获批断档、期初审批、逐科目/维度/币种核对项、废弃批次释放重建范围，以及锁定批次/行的数据库触发器保护。
- 迁移尚未在恢复副本或生产执行；在恢复副本完成 `upgrade`、`downgrade`、锁定触发器和回滚边界测试前，保持未部署状态。

## 2026-07-30 连通性恢复与恢复副本前置复核

- SSH 已恢复。2026-07-30 01:03 UTC 生产主机 `hbreare-server` 在线，`huabang-backend.service` 为 `active`，`/health` 显示数据库、Redis 已连接；运行提交仍为 `bcdc1e9`。
- 本地当前工作树干净，后续期初工作流提交最高为 `dda0e6b`，包含未部署的数据库迁移 `016cfd3c1454`；尚不可将本地迁移或代码状态表述为生产完成。
- 恢复副本、备份可用性、生产数据库角色与远程分支仍需重新只读核实；在此之前禁止迁移与开写。
- 2026-07-30 首次读取计划时使用错误仓库根 `D:\huabang` 查找 `.planning`，未发生写入；已转入唯一目标工作树的活动计划。
- 生产数据库只读探针首次因远程 shell 与 Python f-string 的转义冲突而在 Python 解析阶段失败，未建立数据库连接；下一次改用 `.format()` 并保留同一只读查询范围。
- 改用 SQLAlchemy async 引擎后，生产只读探针确认运行身份为 `huabang`、数据库为 `huabang_ai`、PostgreSQL 16.14、生产 Alembic 版本为 `1fdf4577d7d8`；该身份对 `fin_current`、`fin_history`、`fin_read` 的 `USAGE` 和 `CREATE` 均为 false。后续需判断服务实际注入环境是否与 shell 配置一致，不能假设已存在最小权限角色。
- 后续探针尝试直接在远程 heredoc 中查询可见 schema 时再次遇到 shell 转义语法错误，未执行 SQL；改用 base64 传输 Python 只读探针。
- 将远程 probe 改为 base64 脚本传输后，`awk` 的 `$2` 仍被本地 PowerShell 插值破坏；没有执行数据库 SQL。下一次改为不含 `$` 的 `sed` 变换，避免重复同一转义方式。
- 第三种 probe（base64 Bash 加 `sed`）成功：systemd 读取 `/srv/huabang-ai-center/backend/.env`；应用身份能枚举三个财务 schema 但看不到表。生产与本地 migration head、远程功能分支均存在差异，未作推送、迁移或部署。
- 恢复副本 Gate：`huabang_finance_v2_restore_20260730` 未创建。应用账户执行 `CREATE DATABASE` 得到 PostgreSQL `InsufficientPrivilegeError`；此前以数据库对象权限代替 `CREATEDB` 属性的探针结论已纠正。需要 DBA/超级用户创建独立恢复库并授予恢复所需最小权限，或提供已有恢复副本；在此之前禁止生产迁移。

## 2026-07-30 Phase 4.5 期初工作台补齐

- 以失败测试驱动增加 V2 期初批次列表、草稿创建、平衡验证和最终锁定接口，以及工作台的人工核对界面。验证不改变账簿边界；最终锁定须单独 `cutover_enabled` Gate，且不会开启 draft/review/post Gate。
- 后端定向回归 `28 passed`。一次组合验证在 `backend` 工作目录误执行前端 Node/NPM 命令，产生路径不存在错误，未执行前端验证；下一次切换至 `frontend` 工作目录重跑。
- 完整 V2 回归通过 `131 passed`（1 条既有 Pydantic 未来弃用警告）；本地 Alembic 单一 head 为 `016cfd3c1454`，后端 compileall 与前端静态测试、类型检查、生产构建均通过。
- 原实施计划列出的 `docs/finance/v2.0/api-contract.md` 与 `docs/finance/v2-0-opening-balance-reconciliation.md` 在当前工作树不存在；尚未创建替代文件，先确认有效目录与现有文档再补齐，不能把缺失文件当成已有交付物。
- 已补齐上述 API 契约和期初核对文档，并更新证据登记册。复审发现验证/锁定命令在状态校验前没有返回已完成命令的原结果；已以失败测试修复为先按命令键/请求哈希幂等返回。预演期初锁定不要求最终切换 Gate，最终期初锁定才要求 `cutover_enabled`。
- 最终本地验证：后端 V2 定向套件 `133 passed`、单一 head `016cfd3c1454`、compileall 通过；前端静态回归 `11 passed`、类型检查与 Vite 构建通过（保留既有依赖警告）。
- 已提交并推送 `e66be05 feat: complete finance V2 opening balance workflow` 到 `origin/feature/huabang-full-finance-center`；生产运行提交仍为 `bcdc1e9`，未迁移、未重启、未开启 Gate。
- 找到可复用恢复副本 `huabang_ai_finance_drill_20260729_r2`，其历史账与当前账状态适合验证 `016cfd3c1454`。但当前可用配置仅含受限 `fin_app` 登录，`fin_migrator`/schema owner 无可用受控连接；迁移测试暂不能执行，不触碰恢复库或生产库。

## 2026-07-30 Phase 5 报表元数据与只读就绪检查

- 以失败测试驱动实现资产负债表/利润表的模板、映射、覆盖范围和会计等式检查。V2 工作台可读取两类报告的结构化就绪结果，但没有正式报表导出或应用侧模板写入入口。
- 新 migration `c82e5a1f9d70` 将模板、映射与快照放入 `fin_current`，并限制 `fin_app` 为只读；已发布/退役模板、非草稿映射和快照均在数据库层拒绝变更。
- 本地完整财务 V2/角色/历史导入定向回归 138 项、前端静态回归 12 项和类型检查/生产构建通过；仍未进行恢复副本迁移测试、生产部署或浏览器验收。

## 2026-07-30 华邦中台来源接入事实核验

- 已在生产对华邦中台 DWD 层执行只读字段/计数/日期核验。销售和退货仅有 2026-06-14 至 06-16 的有限历史数据；费用和现金候选表为空。
- 不把这批经营数据虚构为完整会计事实，也不生成 V2 草稿。来源接入后续仅能按 Phase 6 的受控收件箱和只读 preview 实现，并须先取得完整来源范围与结算事实。

## 2026-07-30 Phase 6 来源收件箱与 dry-run 框架

- 已用测试先行扩展规则选择：仅已发布、业务日期有效且来源/法人/组织/账簿范围匹配的规则可被选中；同级规则冲突、缺规则、无效金额均进入 `pending_mapping`，永不创建草稿。
- 新增来源身份/版本、收件箱、规则版本、映射异常与预览运行模型及只读 API/前端工作台。迁移 `e951b2d0a6c4` 显式撤销 `fin_app` 的来源控制表写权限；没有配置受控导入身份或来源写 API。
- 本地完整财务 V2/角色/历史导入定向套件 `145 passed`，前端静态回归 `13 passed`、类型检查与生产构建通过；必须在恢复副本验证迁移与权限后才可发布，且真实华邦候选数据仍不完整，禁止任何自动草稿。

## 2026-07-30 增量迁移恢复副本演练入口

- 从生产 baseline `1fdf4577d7d8` 到新 head `e951b2d0a6c4` 的静态 SQL 渲染成功；全库零版本渲染被既有数据依赖迁移阻断，不能作为本次增量迁移的否定结论。
- 新增受限 `deploy/rehearse_finance_v2_migrations.sh`，只允许命名为 `huabang_ai_finance_drill_*` 的恢复库，并固定执行 upgrade→downgrade→upgrade 与角色核验；无生产库目标、无 systemd 重启、无 stdin sudo。
- 服务器当前非交互 sudo 被拒绝，因此尚未执行恢复副本的真实 DDL 演练。该事实已记入证据登记册，继续保持生产迁移 No-Go。

## 2026-07-30 旧入口与开写 Gate 文档

- 新增旧财务入口兼容登记册，明确 V2 只读验收时旧正式写路径不能提前关闭，以及最终的草稿→审核→人工过账分阶段切换顺序。
- 新增开写 Gate 手册，将恢复副本、备份恢复、权限浏览器、最终期初、运行保障和旧系统冻结列为独立 No-Go；记录隔离恢复工作树和无密码持久化的交互式 sudo 演练命令。

## 2026-07-30 恢复副本迁移执行

- 项目管理员已在受控 SSH TTY 成功运行隔离恢复库 `huabang_ai_finance_drill_20260729_r2` 的 upgrade→downgrade→upgrade 演练；三项待发布迁移均执行，两次 `verify_finance_database_roles.py` 返回 `status=ready`。等待独立只读探针补记最终表与权限事实。
- 首次独立探针因远程 heredoc 的 SQL 单引号在本地命令转义时被移除而失败，未执行 DDL/DML；下一次改用 base64 传输，避免重复同一转义路径。
- 一次生产 Git 祖先核验命令因 PowerShell 对嵌入的 Python 字典花括号做字符串格式化而在本地中止，未执行远程动作；简化为无花括号命令后确认当前生产备份提交没有源码差异。
- 生产只读发布的 dry preflight 已匹配功能提交 `33d3756`、服务器 canonical manifest SHA-256 `390a3033…e4b7b195` 与历史 339/4,596 输入；`--execute` 尚未执行，等待交互式 sudo TTY。

## 2026-07-30 生产发布状态复核

- 只读 SSH 复核显示生产仍运行 `a52a679894d6e533d87efcb3d79e81b43f696793`，服务 active，健康检查中数据库与 Redis 均 connected。当前不能把恢复副本演练或 dry preflight 表述为生产只读发布。
- 根目录 `.finance-v2-release.lock` 是 2026-07-29 的空遗留文件，未发现持锁发布进程。发布脚本使用 `flock`，因此文件存在不等于互斥锁被占用；未清理或修改该文件。
- 使用当前功能分支头 `a8ede7058504cf3614ec9a71d572bc93a30d1550`、同一金蝶清单哈希及 339/4,596 预期值重新运行发布脚本无写 preflight；输入被成功回显。`--execute` 仍未运行。

## 2026-07-30 生产只读发布失败调查

- 用户已执行 `--execute`。备份、权限引导、三项 V2 迁移、角色核验和权限种子成功；历史导入被 `AIS20251127140257: missing database snapshot metadata` 安全阻断，未完成发布。
- 发布 trap 将运行时代码恢复至 `a52a679`，但生产 database 保持于 `e951b2d0a6c4`；独立 `alembic current` 因旧代码缺少该 revision 而失败。这是当前最高优先级：先查明有效快照与发布脚本 preflight 缺口，再以兼容代码修复生产运行态；禁止手动降库、删除 schema 或开启 V2 Gate。
- 根因调查已确认服务器上只存在一个 manifest，且其 `databases=[]`、不存在 `canonical_import/databases/`，因此不是完整可导入的原生快照。第一次远程 session probe 因 PowerShell 展开 `$FINANCE_*` 而未执行；后续改用 PowerShell 单引号封装整个远程命令。
- 已按测试先行补充发布脚本回归：历史快照 dry-run 必须发生在 `--execute` 分支、`sudo_init`、备份和迁移之前。该测试先失败（缺少该行为），最小实现后 `tests/test_finance_v2_release_assets.py` 为 6 passed。独立 `bash -n` 的首次 Windows 路径调用错误，脚本的同类语法检查已由该测试的 `bash -n` 输入通过；后续使用 WSL 路径或 Python 测试验证，避免此路径形式。
- 已在本地发现完整原生快照根 `D:\huabang\invest_kingdee\results\K3MIG_20260717_172928\manifest.json`，总计 12,826 个文件、403,191,671 字节。该根 manifest 的 loader dry-run 产生 339 凭证、4,596 分录、0 冲突；其 SHA-256 为 `BBE9676545C413A5AE077796D766C04E572A75D1F918B1053FA9548F1D8DB1FD`。Windows `scp -r` 只上传了部分无关文件，未将其表述为完整同步；随后仅显式补齐导入所需 9 个哈希校验表文件与根 manifest 到新的服务器 candidate 目录。该候选在服务器 dry-run 同样为 339/4,596、0 冲突，未覆盖旧 canonical 输入或写入财务表。
