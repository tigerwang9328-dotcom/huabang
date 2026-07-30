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
