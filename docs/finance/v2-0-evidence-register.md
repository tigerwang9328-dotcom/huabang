# 华邦财务中心 V2.0 证据登记册

> 最后核实：2026-07-29（北京时间）。本登记册只陈述带有环境和时间的证据；不以设计、本地测试、部署到磁盘或生产验收互相替代。

## Phase 0 已核实事实

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 本地实施工作树 | `D:\huabang\worktrees\kingdee-finance-local`，分支 `feature/huabang-full-finance-center`；当前只读发布候选代码提交为 `b7c2c134131cec68080a66b49f8732930708bedf`。Finance V2 路由使用单独的 `get_finance_db`；中台 JWT/角色/权限依赖仍使用既有 `get_db`，不存在受限财务角色读取 `sys` 表的授权扩大；发布前须重新核实最终 HEAD 与工作树状态 | 本地，2026-07-29 | 本地只读与本地测试 | 可继续恢复副本演练 |
| 本地迁移图 | `1fdf4577d7d8` 是当前唯一 head；其父为 `9c121d3145d9`，新增 `fin_read.history_import_batch` 只读视图供受限应用监控历史冲突。保留手工损益结转凭证证据、结账批次、双人反结账审批、历史已发布分录只读视图/索引、凭证约束、凭证编号 reservation 审计与 `operation_event` 保护 | 本地，2026-07-29 | 本地只读与本地测试 | 新迁移必须从当天实际图生成并在恢复副本验证 |
| 生产仓库 | `/srv/huabang-ai-center`，分支 `feature/huabang-ai-mvp`，HEAD `1cdafd03674081ad3620ae7d723cf280774f3d0b`，核验时无工作树改动输出 | 生产只读，2026-07-29 | 生产只读 | V2 本地代码尚未部署 |
| 生产后端 | `huabang-backend.service` 为 active/running；以 `xiaohu` 身份在 `127.0.0.1:8000` 运行 Uvicorn，工作目录为 `/srv/huabang-ai-center/backend` | 生产只读，2026-07-29 | 生产只读 | 未授权前不得重启 |
| 生产迁移状态 | Alembic 单一 head/current 均为 `6c1e4a7d2f09` | 生产只读，2026-07-29 | 生产只读 | 发布前必须重新核实并比较本地迁移链 |
| 生产只读发布预检 | 服务 active/enabled；运行环境文件权限 `0600`、归属 `xiaohu:xiaohu`；生产 V2 三 schema 数为 0；五个 `fin_*` 角色均存在且三个登录角色无持久口令；本轮恢复逻辑备份为 63 MB。PostgreSQL `archive_mode=off`、`wal_level=replica`、非恢复模式 | 生产只读，2026-07-29 | 生产只读 | 允许评审只读发布脚本；PITR/RTO 仍未满足，正式当前账写入继续 No-Go |
| 华邦中台权限现状 | `finance_manager` 与 `super_admin` 均存在；`finance_manager` 当前仅有一条 V2 权限记录及一条关联。候选发布的幂等种子只补齐 `finance:center:view`、`finance:center:operate` 与该角色的缺失关联，不分配用户、不修改其他角色 | 生产只读，2026-07-29 | 生产只读与本地代码审查 | 发布后必须重新登录，以超级管理员及已分配财务角色分别验收 |
| 旧财务正式写入口 | 生产 OpenAPI 中现有 `/api/v1/finance-center/kingdee/import`、`/vouchers`、`/vouchers/{id}/post`、`/reverse`、`/revise-entries`，以及旧 `/api/v1/finance/*` 写接口 | 生产只读，2026-07-29 | 生产运行时 | 只读验收期不得关闭或代理这些入口 |
| 金蝶源快照 | `ods.kingdee_import_batch=3`、`ods.kingdee_voucher=339`、`ods.kingdee_voucher_entry=4596`、`ods.kingdee_account=416`、`ods.kingdee_balance=6868`；3 个批次均保存备份/manifest 哈希、预期计数与校验结果 | 生产只读，2026-07-29 | 生产只读 | V2 历史导入必须另建 `fin_history` 暂存—校验—发布链，绝不改写 ODS |
| 本地金蝶 V2 dry-run | 原生快照 `D:\huabang\invest_kingdee\results\K3MIG_20260717_172928` 的 SHA-256/行数已读取校验；仅 3 个 official 账套进入候选集，得到 339 张凭证、4,596 条分录、0 个重复/变更哈希冲突 | 本地，2026-07-29 | 本地只读与本地测试 | 未写数据库；待在恢复副本以 `fin_history_importer` 暂存、校验、发布 |
| 历史数据方向与红字 | 金蝶 `FDC=1` 作为借方、`FDC=0` 作为贷方；`FAmount` 保留其签名，并逐凭证与金蝶表头借/贷签名合计核对。339 张凭证均通过该校验 | 本地，2026-07-29 | 本地只读与本地测试 | 仅适用于 `fin_history` 历史只读事实；不可套用到 `fin_current` 当前账正数分录约束 |
| 金蝶覆盖范围 | 凭证日期为 2025-10-31 至 2026-06-30，来自 3 个 source database | 生产只读，2026-07-29 | 生产只读 | 当前账启用日与 2026-07-01 后连续性尚未获得财务确认 |
| 既有正式账 | 旧 `fin` schema 存在 10 个账簿、349 张凭证和 4,617 条分录；它与 V2 的 `fin_current`/`fin_history` 隔离模型不是同一已验收实现 | 生产只读，2026-07-29 | 生产只读 | 不得把旧表直接宣布为 V2 正式账 |
| V2 写入口保护 | 本地 V2 读/写 API 统一复用华邦中台 JWT、`SysUser`、`SysRole`、`SysPermission`；非管理员必须同时具有 `finance_manager` 角色及 `finance:center:view` 或 `finance:center:operate`，且不存在显式全局 Gate 时写命令 fail-closed | 本地测试，2026-07-29 | 本地测试 | 生产仍需先执行权限种子、重新登录并重新核验，不能据此开启写入 |
| 数据库角色 | PostgreSQL 集群已创建 `fin_schema_owner`、`fin_migrator`、`fin_app`、`fin_history_importer`、`fin_readonly_auditor`，并在恢复副本为 V2 三 schema 配置所有权与最小权限；r2 最终核验确认三个临时登录角色 `fin_migrator`、`fin_history_importer`、`fin_app` 均无持久口令。真实 `fin_app` 会话可读 `fin_current`/`fin_read`、可写 `fin_current`、被数据库拒绝写 `fin_history`。生产 `huabang_ai` 仍未创建 V2 schema、未迁移、未授予 V2 对象权限 | 服务器恢复演练，2026-07-29 | 恢复副本验证与生产控制面变更 | 生产迁移、历史发布和当前账开写仍 No-Go；生产连接配置与受限凭据尚未配置 |
| 备份与恢复 | 已从 `huabang_ai` 新建 custom 逻辑备份 `/var/backups/huabang-finance-v2/huabang_ai_finance_v2_drill_20260729T085500Z.dump`（65,714,187 bytes，SHA-256 `b803172e…c15c8050`），r1 曾恢复并迁移但历史导入揭示 `autoflush=False` 下暂存记录未显式 flush 的缺陷，r1 不作为发布证据。修复后从同一备份新建 r2 `huabang_ai_finance_drill_20260729_r2`，迁移至 `1fdf4577d7d8` 并通过角色与运行时验证；仍未演练 PITR、备份轮换或正式 RTO | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 正式开写仍需 PITR/保留策略/恢复时间证据；不得把本次演练描述为生产发布 |
| 后端 V2 定向测试 | 在临时非生产 `APP_SECRET_KEY`/`DB_PASSWORD`/`JWT_SECRET_KEY` 环境变量下，21 个 `test_finance_v2*.py`、`test_finance_database_roles.py`、`test_import_finance_v2_history_script.py` 共 106 项通过；有 1 条 Pydantic 弃用警告。覆盖中台权限、独立受限会话、最小权限迁移、命令幂等、API fail-closed Gate、金蝶来源哈希/红字校验、历史只读下钻、总账明细分页、结账检查/双人反结账、手工损益结转证据、结账中人工过账阻断、当前账试算表和监控摘要路由 | 本地，2026-07-29 | 本地测试 | 可继续恢复副本导入；不是生产验收 |
| 前端基线 | `finance-v2-core` 静态回归、`npm run type-check` 与 `npm run build` 均退出成功；V2 工作台可展示中台权限入口、历史凭证与分录、手工损益结转凭证登记、结账检查和当前账试算表，构建输出仍包含现有依赖的 Vite/Rollup 警告 | 本地，2026-07-29 | 本地构建 | 不等同于浏览器、恢复副本或生产验收 |
| 恢复副本 V2 迁移与权限 | 以短期 `fin_migrator` 登录并 `SET ROLE fin_schema_owner` 成功将 r2 隔离库从 `6c1e4a7d2f09` 升级到 `1fdf4577d7d8`；`verify_finance_database_roles` 返回 `{"status":"ready","violations":[]}`。`fin_read.history_import_batch` 存在且 `fin_app` 具有 SELECT；最终核验确认 `fin_migrator` 口令已清除 | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 可继续历史暂存/校验/发布演练；不等同于生产迁移、应用切流或生产验收 |
| r2 金蝶历史发布与幂等重跑 | 使用清单 SHA-256 `CE10F6A37FFBE0B6045F4B25D09F1E1E46F882E24DA1564B8513E9B4B56A805E` 的受控最小快照，3 个 official 账套均从 `loaded → validated → published`：77/871、244/3,476、18/249（凭证/分录）。最终为 3 批、339 历史凭证、4,596 历史分录、339 历史来源链接、339 个 `historical_marker=true` 只读视图记录、0 当前账凭证；第二次相同导入三批均为已发布且新增 0，计数不变 | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 历史导入链可继续作为生产 Gate 的证据；不等同于生产历史写入、前端验收或开写授权 |
| r2 `fin_app` 应用会话 | 新代码的 `get_finance_db` 以短期 `fin_app` 登录运行，`current_user=fin_app`；读取 `fin_current.voucher` 和 `fin_read.history_import_batch` 均成功。`fin_app` 对 `fin_current.voucher` 有 INSERT，对 `fin_history.import_batch` 无 INSERT，实际 INSERT 尝试被数据库以 permission denied 拒绝；验证后口令清除，历史与当前账计数仍为 339/4,596/0 | 服务器恢复副本，2026-07-29 | 恢复副本运行时验证 | 证明受限会话可作为生产只读发布的前置；不等同于生产服务重启、平台登录端到端验收或生产开写 |
| 生产库 V2 隔离 | r2 最终核验查询 `huabang_ai` 的 `fin_current`、`fin_history`、`fin_read` schema 数为 0 | 生产数据库只读核验，2026-07-29 | 生产只读 | 证明本轮恢复演练未将 V2 schema 或历史数据写入生产；生产发布仍 No-Go |
| 发布与凭据处理资产 | Linux 发布入口默认 dry-run，必须同时固定远端 ref、预期提交、历史清单 SHA-256 和历史凭证/分录预期数才可 `--execute`；它创建发布前逻辑备份、隔离迁移/导入临时口令、保持 V2 写 Gate 关闭、在失败时仅回退运行时文件。PowerShell 仅 SSH 编排。`alembic.ini` 与四个既有运维脚本已移除内联数据库口令，后者改为受限 `.env` 生成临时 `PGPASSFILE` | 本地，2026-07-29 | 本地测试与代码审查 | 仍须在生产先验证脚本语法/dry-run、历史清单和现有任务调用；不等同于生产凭据已轮换 |
| 首次生产只读发布尝试 | 已建立新的发布前逻辑备份（SHA-256 `a6843390…a577cace`）；随后 bootstrap 在 `postgres` 用户无法读取应用目录 SQL 文件处停止。脚本已回退到旧提交，服务未重启、V2 三 schema 仍为 0、历史数据未写入；根因已在候选提交中改为受控临时 SQL 文件转交 `postgres` 执行 | 生产执行与只读复核，2026-07-29 | 已失败且已回退的发布尝试 | 不得把该次尝试计为部署；修复后必须重新 dry-run 和发布 |
| 第二次生产只读发布尝试 | 已建立新的发布前逻辑备份（SHA-256 `389fbdf4…d65691a8`），V2 三 schema 与全部迁移已成功升级至 `1fdf4577d7d8`；随后角色验证脚本因 `app` 模块路径未注入而停止。脚本已回退到旧代码运行时，服务未重启，`fin_current.voucher=0`、`fin_history.voucher=0`、`fin_history.voucher_line=0`，三个临时登录角色均无持久口令 | 生产执行与只读复核，2026-07-29 | 部分数据库扩展、运行时已回退 | 数据库扩展保留并以前滚方式完成；修复后必须先验证角色脚本，再导入历史与重启服务 |

## 待确认或不可满足项

| 项目 | 状态 | 所需证据/处置 | 对发布的影响 |
| --- | --- | --- | --- |
| 会计政策签字 | 用户授权例外 | 形式签字按 `v2.0/deployment-decisions.md` 忽略；但法人、账套、期间、币种、科目、期初及报表映射仍需可核对事实证据 | 不得把例外当作正式会计依据或法定报表/最终切换批准 |
| 当前账起始日与覆盖缺口 | 待确认 | 确认历史截止日、旧系统最终余额、启用日期与任何 `coverage_gap` | 不得批准最终期初或打开 V2 制单 |
| 生产数据库最小权限 | 恢复副本已验证 | 为生产 `huabang_ai` 配置受限凭据、`CONNECT`、V2 schema 与默认权限，并在不影响现有应用的前提下重新运行验证器 | 生产迁移、发布历史或开写仍 No-Go |
| 生产主应用凭据轮换 | 待执行 | 已从候选源码清除内联口令并改造相关脚本；仍需核验生产现用主应用口令是否受影响、部署新脚本后轮换，并验证后端/备份/定时任务 | 正式开写 No-Go；只读发布脚本仅生成独立 `fin_*` 凭据，不擅自改变主应用登录 |
| 备份恢复演练 | 部分验证 | 已有新鲜逻辑备份、校验和、隔离恢复、迁移和权限验证；仍需 PITR、保留策略、恢复耗时与清理记录 | 只读发布可评审；正式开写 No-Go |
| 性能、告警与浏览器验收 | 未开始 | 按实施计划 Phase 5.5A/5.6 在生产形态环境取得证据 | 正式切换与开写 No-Go |

## 当前 Go / No-Go

- 本地 TDD、迁移设计、恢复副本恢复/迁移/最小权限验证与金蝶历史暂存—校验—发布/幂等重跑：**Go**。
- 生产数据库迁移、任何历史写入、服务重启、旧入口冻结、V2 制单/审核/人工过账：**No-Go**。
- 解除 No-Go 的最小顺序：财务事实口径的可核对证据 → 数据库角色与凭据轮换 → 新鲜备份和恢复演练 → 单一 head/恢复副本迁移 → 生产只读验收 → 最终切换 Gate。

## 生产只读发布实证（2026-07-29，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 生产发布提交 | 发布入口以受控 stdin sudo 执行，运行时代码最终为 `9eb4024cf7741f398010be656c2660c875d6ac84`；`huabang-backend.service` active，启动于 `2026-07-29 12:13:22 UTC` | 生产执行 | 生产运行时 | 仅证明只读发布已切换，不开启写入 |
| 备份与迁移 | 发布前生成 custom 逻辑备份 `huabang_ai_finance_v2_release_20260729T121220Z.dump`，SHA-256 `4754e6a18a0a0f70dbbec1e80ef21be530429793923e88b97fe5c86ec8fd833b`；生产 Alembic 已到 `1fdf4577d7d8` | 生产执行 | 生产执行 | 不替代 PITR、保留策略或 RTO 证据 |
| 历史账发布 | 受控历史清单 SHA-256 `CE10F6A37FFBE0B6045F4B25D09F1E1E46F882E24DA1564B8513E9B4B56A805E` 被校验。生产 `fin_app` 验证器返回 339 历史凭证、4,596 历史分录、0 当前账凭证、无启用 V2 写 Gate | 生产运行时 | 生产运行时 | 历史只读查询 Go；当前账写入继续 No-Go |
| 权限与最小权限 | 权限种子返回 `finance_manager` 已具备 `finance:center:view`、`finance:center:operate`；未分配用户。数据库核验显示财务登录角色中仅 `fin_app` 保有运行所需口令，临时 `fin_migrator` 与 `fin_history_importer` 已清除口令 | 生产执行与数据库只读核验 | 生产控制面与运行时 | 未等同于已分配财务人员或已完成职责分离验收 |
| 前端可达性事故与纠正 | 初次切换后 `/app/dashboard` 为 500，Nginx 日志明确记录 `Permission denied` 与 `internal redirection cycle`；根因是发布全局 `umask 077` 生成 700/600 的 `dist`。已仅修改该静态目录为 755/644；本地 Nginx 仪表盘与 FinanceCenter 资源均为 200，外部匿名浏览器显示华邦登录页。提交 `9eb4024` 在未来发布中加入构建前/切换后 `www-data` 可读性校验 | 生产运行时与外部匿名浏览器 | 故障复现、根因与修复后验证 | 静态前端可用；尚未以已授权财务用户完成浏览器业务验收 |

### 更新后的 Go / No-Go

- **Go：** 生产 Finance V2 历史账只读发布、历史标记保留、受限 `fin_app` 查询和中台权限入口。
- **No-Go：** V2 草稿、财务审核、人工过账、期间结账、来源同步及任何 `fin_current` 写入；原因仍为 PITR/RTO/保留策略、期初与期间连续性和已授权财务用户端到端验收未完成。

## 备份恢复链实证（2026-07-29，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 失效 cron 的根因 | `xiaohu` 的原全库逻辑备份任务把输出重定向至不可写的 `/var/log`；修正日志后，应用数据库账户在 `fin_current` 上被最小权限正确拒绝。该任务已从 crontab 移除，未通过扩大应用权限“修复” | 生产运行时 | 故障复现与根因证据 | 原 cron 不能作为 RPO 证据 |
| 逻辑备份 timer | `huabang-postgres-backup.timer` 已 active；root 拥有的运行脚本以 PostgreSQL OS 用户执行。custom dump `huabang_ai_20260729T125202Z.dump` 及其 SHA-256 清单通过校验 | 生产执行 | 生产备份证据 | 满足本机逻辑恢复前置 |
| WAL 与物理基线 | `archive_mode=on`、归档命令已运行；`pg_stat_archiver` 成功归档且失败数 0。`huabang-postgres-basebackup.timer` 已 active，物理基线包含 `base.tar`、`pg_wal.tar` 与 `SHA256SUMS` | 生产运行时 | 生产 PITR 链路证据 | 可进入隔离 PITR 演练 |
| 隔离 PITR 恢复 | 独立 PostgreSQL 实例使用归档 WAL 在端口 `55432` 恢复后，核验 `alembic=1fdf4577d7d8`、`history_vouchers=339`、`history_entries=4596`、`current_vouchers=0`；第二次完整演练耗时 16 秒且实例自动关闭/清理 | 生产形态隔离恢复 | 恢复演练证据 | 本机 RTO 技术演练通过；不等同于异机灾备 |

**更新后的限制：** PITR 的技术链路已从 “未验证” 更新为 “本机已验证”；由于没有异机或异存储副本，它仍不能证明主机损坏场景下的 RPO/RTO。当前账开写 Gate 继续关闭，直至该副本和期初/期间/业务验收证据齐备。

## 可观测性 Gate 发布实证（2026-07-29，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 策略与接口 | 提交 `8a3dc105cc193f0f0389587532a422494105dec1` 发布 11 项 V2 指标策略。过账失败、历史导入冲突、结账失败返回持久化聚合值；无事实源的借贷不平、来源积压、锁/死锁、导出、5xx、余额差异明确返回 `availability=unavailable` 与原因，不冒充零 | 本地测试、生产磁盘与进程 | 本地回归与生产运行时 | 指标可见性已增强；未接入采集器仍阻断生产开写 |
| 脱敏与通知诚实性 | 所有策略标签为空；不返回凭证、科目、交易对手或用户数据。逻辑通知路由为 `finance-v2-oncall`，但 `notification_configured=false`，工作台显示“待接入” | 本地测试与生产代码 | 本地测试、生产部署 | 不得把策略路由表述为实际通知送达 |
| 工作台与鉴权 | V2 工作台增加“运行监控与告警 Gate”只读区。生产后端重启后 health 显示数据库/Redis connected；监控端点未登录返回 401，OpenAPI 含该路由，前端静态入口 HTTP 200 且 `www-data` 可读 | 生产运行时 | 生产部署验证 | 证明路由受中台鉴权且已加载；尚未完成已登录财务用户浏览器验收 |

**当前限制：** 真实通知通道、API 5xx/锁等待/死锁/余额差异采集、性能基准和一次告警关闭演练尚未完成。它们继续是 V2 正式写入 No-Go，不以工作台可见或接口可达替代。

## 性能 Gate 数据规模核验（2026-07-29，后补）

| 检查项 | 生产只读结果 | 结论 |
| --- | --- | --- |
| `fin_current.voucher` / `voucher_line` / `ledger_balance` / `opening_balance_line` | 全部为 0 行；各表仅有初始空表大小 | 不能用空表测量分页、单凭证过账 P95、月结或余额表性能；性能 Gate 不通过 |
| 已发布历史数据 | `fin_history.voucher=339`、`fin_history.voucher_line=4,596`，最大相关表约 1.3 MB | 仅足以证明历史查询存在，远低于大账簿或百万级测量规模 |
| 允许的下一次测量 | 最终期初批准和受控试点数据出现后，在独立恢复副本/生产形态环境测量并记录 P95、并发、锁等待、死锁和资源限制 | 不能提前以模拟零数据宣布性能通过 |

## 中台权限菜单一致性实证（2026-07-29，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 中台角色实际分配 | `finance_manager`（财务经理）已有 1 名已分配用户，角色包含 `finance:center:view`、`finance:center:operate` 及既有财务权限；未在本次变更中新增或调整用户角色 | 生产数据库只读核验 | 生产控制面证据 | 具备后续受控浏览器验收的账号前提，但尚未完成登录验收 |
| 菜单权限修正 | 侧边栏不再复制财务菜单或以 `finance:profit:view` 控制“财务中心”；改为复用 `financeProfitNavigation` 单一配置，财务中心及其下级菜单统一要求 `finance:center:view` | 本地测试、生产静态资源切换 | 回归测试、类型检查、生产运行时 | 消除旧利润权限与财务中心权限的漂移；不改变任何角色授权 |
| 生产静态资源验证 | 代码提交 `872cb674554b8dd8ed86d0b28a15c41ecc15d725` 已在 `/srv/huabang-ai-center`；服务器完成类型检查与构建，候选静态目录经 `www-data` 读取验证后原子切换。`/app/dashboard`、`/app/finance-center/core-workspace` 均为 HTTP 200，后端保持 active | 生产运行时 | 生产部署验证 | 菜单与路由可达；未等同于已登录财务用户端到端验收 |
| 写入保护复核 | `fin_current.feature_gate` 无启用记录，`fin_current.voucher=0` | 生产数据库只读核验 | 生产运行时 | 本次只发布前端权限一致性，不开启草稿、审核、过账或结账 |

## 当前账凭证工作台发布实证（2026-07-29，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 发布提交与范围 | `/srv/huabang-ai-center` 已切换至 `367bbeea56d94777f3a7d337c1a801e3159a4994`。本次仅发布凭证详情/草稿编辑 API、审计展示和前端工作台；不含 Alembic 迁移、不执行历史导入、不修改功能 Gate | 生产执行，2026-07-29 14:28 UTC | 生产磁盘与运行时 | 不改变已关闭的当前账写入范围 |
| 草稿服务保护 | 草稿创建会写入分录汇总和可追溯的创建命令 ID；草稿整体替换仅限 `draft` 状态，使用命令幂等和版本比较，且拒绝关闭期间或期间外日期。非草稿、并发旧版本不会先删除分录 | 本地 TDD 与回归 | 本地测试 | 证明实现具备受控开写前置，不等同于生产已允许写入 |
| 生产运行验证 | `huabang-backend.service` 重启后为 `active`；`/health` 返回数据库和 Redis connected。`/api/v1/finance-center/v2/monitoring/summary` 未登录返回 401；OpenAPI 含 `/api/v1/finance-center/v2/vouchers/{voucher_id}` 的 GET、PUT；`/app/finance-center/core-workspace` 返回 200 | 生产运行时，2026-07-29 14:28–14:30 UTC | 生产运行时 | 后端已加载、路由仍受中台鉴权；不构成已登录用户业务验收 |
| 本地回归 | 财务后端定向套件 119 passed；前端静态回归 10 passed、`vue-tsc --noEmit` 与 Vite 构建成功。构建仅保留既有 Vite CJS / Rollup 注释警告 | 本地，2026-07-29 | 本地测试与构建 | 可作为发布代码质量证据，不替代生产写入或浏览器验收 |

**保持 No-Go：** 本次未开启 `draft_enabled`、`review_enabled`、`post_enabled` 或 `period_close_enabled`，也未生成当前账凭证。异机/异存储恢复、最终期初与期间连续性、非空生产形态性能数据、真实告警通知闭环，以及已登录财务/超级管理员浏览器验收仍是正式开写前置。

## 期初工作流与生产连接复核（2026-07-30，后补）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 本地期初工作流 | 本地新增期初批次的列表、草稿创建、验证和锁定 API，以及工作台人工核对入口。批次状态为 `draft → validated → locked`；验证不改变账簿启用边界，最终锁定额外要求 `cutover_enabled`，且不自动开启 draft/review/post Gate。命令在状态检查前按命令键和请求哈希返回原结果，避免网络重试造成假冲突 | 本地，2026-07-30 | 本地测试与构建 | 代码可继续进入恢复副本验证；不代表生产已部署或允许开写 |
| 本地验证 | 财务 V2、数据库角色与历史导入定向套件共 131 项通过；期初增量定向套件 29 项通过；前端静态回归 11 项、`vue-tsc --noEmit` 与 Vite 构建均通过。仅有既有 Pydantic 弃用和 Vite/Rollup 注释警告 | 本地，2026-07-30 | 本地测试与构建 | 不替代恢复副本、生产迁移或已登录浏览器验收 |
| 生产服务与代码 | `hbreare-server` 可达，`huabang-backend.service` 为 active；运行提交 `bcdc1e932e448908e25601f2ba03eb1386f7c77b`，生产 Alembic head 为 `1fdf4577d7d8`。本地工作树 head 已到 `dda0e6b`，其中包含未部署的 `016cfd3c1454` 期初控制迁移 | 生产只读与本地，2026-07-30 | 生产运行时与本地 Git | 新期初工作流未部署；禁止将本地新 head 当成生产完成 |
| 生产专用财务会话 | 实际 V2 会话为 `fin_app`，对 `fin_current` 与 `fin_read` 有 USAGE、无 CREATE；对 `fin_history` 无 schema USAGE。它可读已发布视图（339 历史凭证、4,596 历史分录）、可读当前账 0 凭证与 0 启用 Gate；直接读取 `fin_history` 与 `alembic_version` 均被拒绝 | 生产只读，2026-07-30 | 生产运行时 | 最小权限边界仍有效；通用 `huabang` 账户探针不能替代 `fin_app` 结论 |
| 恢复副本可用性 | `/srv/huabang-ai-center/backups/pre_finance_center_db_20260720T082348Z.dump` 为 PostgreSQL 16 custom archive，位于与项目相同文件系统。通用应用账户创建独立恢复库被 PostgreSQL 拒绝，未创建任何库；因此本轮未对 `016cfd3c1454` 完成恢复副本 upgrade/downgrade/触发器验证 | 生产只读与受控失败尝试，2026-07-30 | 生产控制面 | 新迁移和任何部署维持 No-Go，直至由 PostgreSQL DBA 创建/提供独立恢复副本并完成验证 |

**当前新增 No-Go：** `016cfd3c1454` 的期初控制迁移尚未在恢复副本通过。即使生产历史只读查询可用，也不得部署该迁移、开启 `cutover_enabled` 或创建/锁定生产期初批次。

## 报表元数据与只读就绪检查（2026-07-30，本地）

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 版本化元数据 | 新 migration `c82e5a1f9d70` 定义 `fin_current.report_template`、`report_mapping`、`report_snapshot`。模板要求非空行定义和发布审批信息；映射倍率不得为零。应用角色 `fin_app` 被显式撤销三张表的 INSERT/UPDATE/DELETE。 | 本地代码审阅，2026-07-30 | 本地代码 | 尚未迁移或授予生产对象权限；不构成正式报表发布。 |
| 不可变性与阻断 | 已发布模板只能退役，退役模板、非草稿模板映射与报告快照由数据库触发器拒绝变更。只读 API 对缺模板/映射、已批准覆盖断档、资产负债不平和账簿阻断返回结构化状态；没有导出或生成正式报表的 API。 | 本地 TDD 与代码审阅，2026-07-30 | 本地测试与代码 | 保持“先映射核对、后报告发布”的 No-Go。 |
| 本地验证 | 财务 V2、角色与历史导入定向套件 `138 passed`；Alembic 单一 head 为 `c82e5a1f9d70`；后端 compileall、前端静态回归 `12 passed`、`vue-tsc --noEmit` 和 Vite build 均通过。保留既有 Pydantic、Vite CJS 和 Rollup 注释警告。 | 本地，2026-07-30 | 本地测试与构建 | 不替代恢复副本迁移/降级/触发器验证、生产部署或已登录浏览器验收。 |

**新增 No-Go：** `c82e5a1f9d70` 依赖未验证的 `016cfd3c1454`，两者必须先以 `fin_migrator`/`fin_schema_owner` 在独立恢复副本完成升级、降级和权限验证，才可评审只读生产发布。
