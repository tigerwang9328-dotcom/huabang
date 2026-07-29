# 华邦财务中心 V2.0 发布基线

> 建立时间：2026-07-29（北京时间）。每次生产部署、迁移、恢复副本演练与切换前必须重新采集，而不是复用本文件中的 revision 或提交。

## 代码与运行时基线

| 位置 | 事实 | 状态 |
| --- | --- | --- |
| 本地工作树 | `feature/huabang-full-finance-center`；只读发布候选为 `b7c2c134131cec68080a66b49f8732930708bedf`（Finance V2 数据会话与中台鉴权会话分离、过账尝试使用受限会话、历史批次状态经 `fin_read` 公开、总账明细分页修复，以及受控 Linux 发布入口/只读验证器/中台权限幂等种子；以发布前重新核实的最终提交为准） | 已核实，本地未发布 |
| 本地 Alembic | 单一 head `1fdf4577d7d8`（父 `9c121d3145d9`）；新增 `fin_read.history_import_batch` 只读视图。仍含凭证明细约束、凭证编号审计表、`operation_event` 追加写保护、历史分录只读视图/索引、结账批次/双人反结账审批与手工损益结转凭证证据表；首两条 V2 迁移只验证管理员 bootstrap schema，绝不申请数据库级 CREATE | 已核实，已在恢复副本执行，尚未在生产执行 |
| 生产仓库 | `feature/huabang-ai-mvp` / `1cdafd03674081ad3620ae7d723cf280774f3d0b` | 已核实，未部署 V2 本地分支 |
| 生产 Alembic | 单一 head/current `6c1e4a7d2f09` | 已核实，发布前须再次执行 `alembic heads --verbose` 与 `alembic current --verbose` |
| 生产运行方式 | `huabang-backend.service` → Uvicorn `app.main:app`，监听 `127.0.0.1:8000`，Nginx active | 已核实；只有 Gate 全通过后才允许重启 |
| 生产数据库角色 | 2026-07-29 已备份全局角色定义后，在 PostgreSQL 集群创建五个无持久口令的 `fin_*` 角色；生产 `huabang_ai` 仍没有 V2 schema/迁移/应用连接切换，V2 对象权限只在隔离恢复副本设置 | 已核实；生产最小权限与连接配置仍须在发布 Gate 中单独执行 |
| 生产恢复能力 | 发布前新鲜逻辑备份存在，且 r2 隔离恢复通过；生产 PostgreSQL 仍为 `archive_mode=off`，没有已验证的 PITR、保留策略或 RTO 证据 | 只读发布可在独立备份后评审；正式当前账写入不得放行 |
| 恢复副本演练 | 旧 r1 副本曾暴露暂存记录未 flush、却表面显示发布的缺陷，保留为失败演练证据而非发布结果；使用同一已校验备份新建的 r2 `huabang_ai_finance_drill_20260729_r2` 已升级至 `1fdf4577d7d8`，三 schema 与角色验证均通过。r2 使用受控快照发布 3 批金蝶历史：339 张凭证、4,596 条分录、339 个历史标记、0 个 `fin_current.voucher`；重跑新增 0，计数不变。应用 `get_finance_db` 实际以 `fin_app` 连接，能读 `fin_current`/`fin_read`、能写 `fin_current`、不能写 `fin_history` | 已核实，恢复副本，不是生产部署 |
| 本地后端验证 | V2 定向测试、角色核验和历史导入命令测试 106 passed（临时非生产配置，另有 1 条 Pydantic 弃用警告）；含中台权限、职责分离、独立 `fin_app` 会话、最小权限迁移、独立过账尝试审计、凭证命令幂等、锁定式编号、结账中人工过账阻断、手工损益结转证据、结账检查/双人反结账、历史分录下钻、总账明细分页、当前账试算表与监控摘要 | 已核实 |
| 本地前端验证 | 财务中心中台权限入口、服务端 Gate 就绪状态、受控草稿/命令工作台、历史金蝶分录下钻、手工损益结转凭证登记、结账检查与当前账试算表回归，类型检查与 Vite 构建成功 | 已核实 |

## 回滚基线与限制

1. 真实 V2 当前账写入发生前，只有在冻结窗口内、已演练的恢复流程可用时才可恢复备份。
2. 真实 V2 当前账写入发生后，业务问题只能前向修复；数据库灾难才按已验证 PITR/备份恢复流程，并重放和核对 RPO 范围内交易。
3. 恢复副本逻辑恢复、迁移和权限演练已通过，但 PITR、保留策略和正式 RTO 尚未验证，不能把本表视为生产回滚授权。
4. 旧 `/api/v1/finance/*` 与 `/api/v1/finance-center/*` 写入口在 V2 只读验收期保持原状；最终切换前不得关闭。

## 历史源候选基线

| 项目 | 事实 | 状态 |
| --- | --- | --- |
| 本地金蝶迁移快照 | `D:\huabang\invest_kingdee\results\K3MIG_20260717_172928`，清单 SHA-256：`BBE9676545C413A5AE077796D766C04E572A75D1F918B1053FA9548F1D8DB1FD` | 已核实，本地只读候选源，未导入 V2 |
| 清单结果 | 4 个账套、0 个清单错误；3 个 official 账套合计 339 张凭证、4,596 条分录；另有 1 个空 test 账套。用于恢复演练的最小受控副本清单 SHA-256 为 `CE10F6A37FFBE0B6045F4B25D09F1E1E46F882E24DA1564B8513E9B4B56A805E`，r2 已完成暂存、校验与发布；生产仍未导入 | 已核实，恢复副本已验证，生产未导入 |

历史源使用及切换授权边界见 `v2.0/deployment-decisions.md`。不得将本地快照描述为已写入生产或已完成财务核对。

## 2026-07-29 生产只读发布实际结果（覆盖上方预发布状态）

| 项目 | 实际结果 | 验证状态 |
| --- | --- | --- |
| 生产代码与服务 | `/srv/huabang-ai-center` 已切换到 `9eb4024cf7741f398010be656c2660c875d6ac84`；`huabang-backend.service` active，启动时间 `2026-07-29 12:13:22 UTC` | 已核实，生产运行时 |
| 迁移与备份 | Alembic 已到唯一 head `1fdf4577d7d8`。发布前 custom 逻辑备份为 `/var/backups/huabang-finance-v2/huabang_ai_finance_v2_release_20260729T121220Z.dump`，SHA-256 `4754e6a18a0a0f70dbbec1e80ef21be530429793923e88b97fe5c86ec8fd833b` | 已核实，生产执行 |
| 金蝶历史账 | 受控清单 `CE10F6A37FFBE0B6045F4B25D09F1E1E46F882E24DA1564B8513E9B4B56A805E` 对应 3 个 official 账套；`fin_app` 只读验证为 339 张历史凭证、4,596 条历史分录、0 张当前账凭证 | 已核实，生产运行时 |
| 中台与数据库边界 | 已幂等补齐 `finance_manager` 的 `finance:center:view`、`finance:center:operate`；未分配用户。实际验证会话为 `fin_app`；四个财务登录角色中仅运行所需的 `fin_app` 保有口令，临时迁移/导入角色口令已清除 | 已核实，生产执行与数据库只读核验 |
| 写入控制 | `draft_enabled`、`review_enabled`、`post_enabled`、`period_close_enabled`、`source_sync_enabled` 均未启用（计数 0）；旧财务写入口未冻结、未改写 | 已核实，生产运行时 |
| 前端与公网 | 发布后曾因发布脚本全局 `umask 077` 令新 `dist` 为 700/600，Nginx `www-data` 无法读取并返回 500。已将仅有的静态构建产物修正为目录 755、文件 644；本地 Nginx 的 `/app/dashboard` 与 FinanceCenter 资源均为 200，外部浏览器到达华邦登录页。候选发布脚本现已加入构建前/切换后 `www-data` 可读性校验，防止复发 | 已核实，生产运行时与外部匿名浏览器 |

### 当前发布结论

- **Go：** Finance V2 历史账只读查询、中台权限入口与前端静态资源已完成生产部署；历史数据保留历史标记，未写回金蝶来源表。
- **No-Go：** V2 草稿、审核、人工过账、结账、来源同步以及任何当前账写入仍关闭。`archive_mode=off`、PITR/RTO/保留策略、期初与期间连续性、已授权财务用户的浏览器端到端验收尚未补齐，不能把本次只读发布表述为正式财务切换或可记账上线。

## 2026-07-29 备份、WAL 与恢复演练实际结果（覆盖上方旧恢复状态）

| 项目 | 实际结果 | 验证状态 |
| --- | --- | --- |
| 逻辑备份运行主体 | 原 `xiaohu` cron 使用应用数据库账户执行全库 `pg_dump`：先因 `/var/log` 不可写而未实际运行，修正日志后又因最小权限不能锁定 `fin_current` 而失败。该 cron 已移除，未扩大应用账户权限 | 已核实，生产故障复现与纠正 |
| 受控逻辑备份 | `huabang-postgres-backup.timer` 已启用；服务以 PostgreSQL OS 用户运行、备份运行脚本为 root 拥有。生成 custom 备份 `/var/backups/huabang-postgres/huabang_ai_20260729T125202Z.dump`，SHA-256 校验通过 | 已核实，生产执行 |
| WAL/PITR | PostgreSQL `archive_mode=on`、`archive_timeout=15min`，归档脚本为 root 拥有；物理基线 timer 已启用。`pg_stat_archiver` 核验归档成功且失败数为 0 | 已核实，生产运行时 |
| 物理基线与恢复 | 物理基线 `base_20260729T130303Z` 已生成（含 `base.tar`、`pg_wal.tar` 与校验清单）。在独立端口 `55432`、独立数据目录完成第二次 PITR 恢复，核验 Alembic `1fdf4577d7d8`、339 历史凭证、4,596 历史分录、0 当前账凭证；恢复耗时 16 秒，实例已关闭并自动清理 | 已核实，生产形态隔离恢复 |

本机恢复链已满足技术演练的 RPO/RTO Gate；但备份、WAL 与恢复目录仍在同一服务器磁盘，不能覆盖主机级故障。正式开写仍需至少一份异机/异存储副本及相应恢复演练证据。

## 2026-07-29 中台权限菜单一致性更新

- 生产 `finance_manager` 角色已有 1 名已分配用户，且角色实际包含 `finance:center:view`、`finance:center:operate`；本次未增加用户或扩大角色权限。
- 前端提交 `872cb674554b8dd8ed86d0b28a15c41ecc15d725` 已部署：财务利润下的“财务中心”改为复用统一导航配置，因此只由 `finance:center:view` 显示，不再错误依赖 `finance:profit:view`。
- 服务器构建、`www-data` 静态读取检查、`/app/dashboard` 与 `/app/finance-center/core-workspace` HTTP 200 均已核验；后端未重启且保持 active。
- 当前 `fin_current.feature_gate` 无启用记录、`fin_current.voucher=0`。该变更不构成浏览器登录验收，也不解除当前账写入 No-Go。

## 2026-07-29 可观测性 Gate 更新

- 提交 `8a3dc105cc193f0f0389587532a422494105dec1` 已在生产后端重启加载，前端工作台已原子切换。health 显示数据库与 Redis connected，`/api/v1/finance-center/v2/monitoring/summary` 未登录为 401，OpenAPI 路由存在，静态文件仍经 `www-data` 读取校验。
- 11 项策略均显示阈值、责任人、逻辑通知路由和关闭条件；只有过账失败、历史冲突、结账失败有已持久化聚合值。其他未接入项目明确显示 unavailable，且所有策略 `notification_configured=false`，不得描述为真实告警已经送达。
- 本次仍未开启 `fin_current` 写 Gate、未创建当前账凭证、未完成已登录财务用户验收。性能测量、真实通知演练、异机恢复、最终期初/期间连续性和最终切换继续是正式开写前置。

## 2026-07-29 性能 Gate 现状

生产只读核验确认 `fin_current.voucher`、`voucher_line`、`ledger_balance`、`opening_balance_line` 全部为 0 行；历史账仅 339 张凭证、4,596 条分录。当前不能用空表查询、静态构建或历史小样本替代百万级余额表、大账簿分页、单凭证过账 P95、月结、并发、锁等待/死锁和导出资源限制测量。性能 Gate 明确保持 No-Go，待最终期初与受控试点数据进入恢复副本/生产形态环境后实测。

## 2026-07-29 当前账凭证工作台更新

- 生产运行时代码为 `367bbeea56d94777f3a7d337c1a801e3159a4994`；本次无数据库迁移、无历史导入、无功能 Gate 修改。
- V2 新增当前账凭证详情与草稿编辑契约：`GET`/`PUT /api/v1/finance-center/v2/vouchers/{voucher_id}`。编辑仅接受草稿状态、同一会计期间内的日期和匹配版本；命令 ID 绑定输入哈希，重试不会重复替换分录。
- 草稿创建/编辑同步凭证头借贷合计；创建操作事件使用请求 ID 作为审计命令 ID，修复了此前创建事件参数不完整会在实际写入路径失败的缺陷。
- 生产重启后服务 active，health 显示数据库、Redis connected；新增路由已出现在 OpenAPI，未登录 V2 端点仍为 401，静态工作台为 HTTP 200。
- 本地验证为财务后端 119 passed、前端静态 10 passed、类型检查和生产构建成功。仍未进行已登录财务用户浏览器验收，且所有当前账写 Gate 保持关闭。
