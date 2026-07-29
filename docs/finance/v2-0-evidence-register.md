# 华邦财务中心 V2.0 证据登记册

> 最后核实：2026-07-29（北京时间）。本登记册只陈述带有环境和时间的证据；不以设计、本地测试、部署到磁盘或生产验收互相替代。

## Phase 0 已核实事实

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 本地实施工作树 | `D:\huabang\worktrees\kingdee-finance-local`，分支 `feature/huabang-full-finance-center`；本轮财务代码基线提交为 `70a43ebec0d2e08a32f319712606445d4e6be2fb`，历史导入已在同一事务中显式 flush 暂存记录，且空暂存不得校验或发布；发布前须重新核实最终 HEAD 与工作树状态 | 本地，2026-07-29 | 本地只读 | 可继续恢复副本演练 |
| 本地迁移图 | `9c121d3145d9` 是当前唯一 head；其父为 `232ec287c52f`，新增 V2 手工损益结转凭证证据，且保留结账批次、双人反结账审批、历史已发布分录只读视图/索引、凭证约束、凭证编号 reservation 审计与 `operation_event` 保护 | 本地，2026-07-29 | 本地只读与本地测试 | 新迁移必须从当天实际图生成并在恢复副本验证 |
| 生产仓库 | `/srv/huabang-ai-center`，分支 `feature/huabang-ai-mvp`，HEAD `1cdafd03674081ad3620ae7d723cf280774f3d0b`，核验时无工作树改动输出 | 生产只读，2026-07-29 | 生产只读 | V2 本地代码尚未部署 |
| 生产后端 | `huabang-backend.service` 为 active/running；以 `xiaohu` 身份在 `127.0.0.1:8000` 运行 Uvicorn，工作目录为 `/srv/huabang-ai-center/backend` | 生产只读，2026-07-29 | 生产只读 | 未授权前不得重启 |
| 生产迁移状态 | Alembic 单一 head/current 均为 `6c1e4a7d2f09` | 生产只读，2026-07-29 | 生产只读 | 发布前必须重新核实并比较本地迁移链 |
| 旧财务正式写入口 | 生产 OpenAPI 中现有 `/api/v1/finance-center/kingdee/import`、`/vouchers`、`/vouchers/{id}/post`、`/reverse`、`/revise-entries`，以及旧 `/api/v1/finance/*` 写接口 | 生产只读，2026-07-29 | 生产运行时 | 只读验收期不得关闭或代理这些入口 |
| 金蝶源快照 | `ods.kingdee_import_batch=3`、`ods.kingdee_voucher=339`、`ods.kingdee_voucher_entry=4596`、`ods.kingdee_account=416`、`ods.kingdee_balance=6868`；3 个批次均保存备份/manifest 哈希、预期计数与校验结果 | 生产只读，2026-07-29 | 生产只读 | V2 历史导入必须另建 `fin_history` 暂存—校验—发布链，绝不改写 ODS |
| 本地金蝶 V2 dry-run | 原生快照 `D:\huabang\invest_kingdee\results\K3MIG_20260717_172928` 的 SHA-256/行数已读取校验；仅 3 个 official 账套进入候选集，得到 339 张凭证、4,596 条分录、0 个重复/变更哈希冲突 | 本地，2026-07-29 | 本地只读与本地测试 | 未写数据库；待在恢复副本以 `fin_history_importer` 暂存、校验、发布 |
| 历史数据方向与红字 | 金蝶 `FDC=1` 作为借方、`FDC=0` 作为贷方；`FAmount` 保留其签名，并逐凭证与金蝶表头借/贷签名合计核对。339 张凭证均通过该校验 | 本地，2026-07-29 | 本地只读与本地测试 | 仅适用于 `fin_history` 历史只读事实；不可套用到 `fin_current` 当前账正数分录约束 |
| 金蝶覆盖范围 | 凭证日期为 2025-10-31 至 2026-06-30，来自 3 个 source database | 生产只读，2026-07-29 | 生产只读 | 当前账启用日与 2026-07-01 后连续性尚未获得财务确认 |
| 既有正式账 | 旧 `fin` schema 存在 10 个账簿、349 张凭证和 4,617 条分录；它与 V2 的 `fin_current`/`fin_history` 隔离模型不是同一已验收实现 | 生产只读，2026-07-29 | 生产只读 | 不得把旧表直接宣布为 V2 正式账 |
| V2 写入口保护 | 本地 V2 读/写 API 统一复用华邦中台 JWT、`SysUser`、`SysRole`、`SysPermission`；非管理员必须同时具有 `finance_manager` 角色及 `finance:center:view` 或 `finance:center:operate`，且不存在显式全局 Gate 时写命令 fail-closed | 本地测试，2026-07-29 | 本地测试 | 生产仍需先执行权限种子、重新登录并重新核验，不能据此开启写入 |
| 数据库角色 | PostgreSQL 集群已创建 `fin_schema_owner`、`fin_migrator`、`fin_app`、`fin_history_importer`、`fin_readonly_auditor`，并在恢复副本为 V2 三 schema 配置所有权与最小权限；r2 最终核验确认 `fin_migrator` 与 `fin_history_importer` 均无持久口令。生产 `huabang_ai` 仍未创建 V2 schema、未迁移、未授予 V2 对象权限 | 服务器恢复演练，2026-07-29 | 恢复副本验证与生产控制面变更 | 生产迁移、历史发布和当前账开写仍 No-Go；生产连接配置与受限凭据尚未配置 |
| 备份与恢复 | 已从 `huabang_ai` 新建 custom 逻辑备份 `/var/backups/huabang-finance-v2/huabang_ai_finance_v2_drill_20260729T085500Z.dump`（65,714,187 bytes，SHA-256 `b803172e…c15c8050`），r1 曾恢复并迁移但历史导入揭示 `autoflush=False` 下暂存记录未显式 flush 的缺陷，r1 不作为发布证据。修复后从同一备份新建 r2 `huabang_ai_finance_drill_20260729_r2`，迁移至 `9c121d3145d9` 并通过角色验证；仍未演练 PITR、备份轮换或正式 RTO | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 正式开写仍需 PITR/保留策略/恢复时间证据；不得把本次演练描述为生产发布 |
| 后端 V2 定向测试 | 在临时非生产 `APP_SECRET_KEY`/`DB_PASSWORD`/`JWT_SECRET_KEY` 环境变量下，20 个 `test_finance_v2*.py`、`test_finance_database_roles.py`、`test_import_finance_v2_history_script.py` 共 96 项通过；有 1 条 Pydantic 弃用警告。覆盖中台权限、最小权限迁移、命令幂等、API fail-closed Gate、金蝶来源哈希/红字校验、历史只读下钻、结账检查/双人反结账、手工损益结转证据、结账中人工过账阻断、当前账试算表和监控摘要路由 | 本地，2026-07-29 | 本地测试 | 可继续恢复副本导入；不是生产验收 |
| 前端基线 | `finance-v2-core` 静态回归、`npm run type-check` 与 `npm run build` 均退出成功；V2 工作台可展示中台权限入口、历史凭证与分录、手工损益结转凭证登记、结账检查和当前账试算表，构建输出仍包含现有依赖的 Vite/Rollup 警告 | 本地，2026-07-29 | 本地构建 | 不等同于浏览器、恢复副本或生产验收 |
| 恢复副本 V2 迁移与权限 | 以短期 `fin_migrator` 登录并 `SET ROLE fin_schema_owner` 成功将 r2 隔离库从 `6c1e4a7d2f09` 升级到 `9c121d3145d9`；`verify_finance_database_roles` 返回 `{"status":"ready","violations":[]}`，最终核验确认 `fin_migrator` 口令已清除 | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 可继续历史暂存/校验/发布演练；不等同于生产迁移、应用切流或生产验收 |
| r2 金蝶历史发布与幂等重跑 | 使用清单 SHA-256 `CE10F6A37FFBE0B6045F4B25D09F1E1E46F882E24DA1564B8513E9B4B56A805E` 的受控最小快照，3 个 official 账套均从 `loaded → validated → published`：77/871、244/3,476、18/249（凭证/分录）。最终为 3 批、339 历史凭证、4,596 历史分录、339 历史来源链接、339 个 `historical_marker=true` 只读视图记录、0 当前账凭证；第二次相同导入三批均为已发布且新增 0，计数不变 | 服务器恢复副本，2026-07-29 | 恢复副本验证 | 历史导入链可继续作为生产 Gate 的证据；不等同于生产历史写入、前端验收或开写授权 |
| 生产库 V2 隔离 | r2 最终核验查询 `huabang_ai` 的 `fin_current`、`fin_history`、`fin_read` schema 数为 0 | 生产数据库只读核验，2026-07-29 | 生产只读 | 证明本轮恢复演练未将 V2 schema 或历史数据写入生产；生产发布仍 No-Go |

## 待确认或不可满足项

| 项目 | 状态 | 所需证据/处置 | 对发布的影响 |
| --- | --- | --- | --- |
| 会计政策签字 | 用户授权例外 | 形式签字按 `v2.0/deployment-decisions.md` 忽略；但法人、账套、期间、币种、科目、期初及报表映射仍需可核对事实证据 | 不得把例外当作正式会计依据或法定报表/最终切换批准 |
| 当前账起始日与覆盖缺口 | 待确认 | 确认历史截止日、旧系统最终余额、启用日期与任何 `coverage_gap` | 不得批准最终期初或打开 V2 制单 |
| 生产数据库最小权限 | 恢复副本已验证 | 为生产 `huabang_ai` 配置受限凭据、`CONNECT`、V2 schema 与默认权限，并在不影响现有应用的前提下重新运行验证器 | 生产迁移、发布历史或开写仍 No-Go |
| 凭据轮换 | 不满足 | 轮换已暴露于备份脚本的数据库凭据，迁移为受限凭据来源，复核备份作业 | 生产发布与开写 No-Go |
| 备份恢复演练 | 部分验证 | 已有新鲜逻辑备份、校验和、隔离恢复、迁移和权限验证；仍需 PITR、保留策略、恢复耗时与清理记录 | 只读发布可评审；正式开写 No-Go |
| 性能、告警与浏览器验收 | 未开始 | 按实施计划 Phase 5.5A/5.6 在生产形态环境取得证据 | 正式切换与开写 No-Go |

## 当前 Go / No-Go

- 本地 TDD、迁移设计、恢复副本恢复/迁移/最小权限验证与金蝶历史暂存—校验—发布/幂等重跑：**Go**。
- 生产数据库迁移、任何历史写入、服务重启、旧入口冻结、V2 制单/审核/人工过账：**No-Go**。
- 解除 No-Go 的最小顺序：财务事实口径的可核对证据 → 数据库角色与凭据轮换 → 新鲜备份和恢复演练 → 单一 head/恢复副本迁移 → 生产只读验收 → 最终切换 Gate。
