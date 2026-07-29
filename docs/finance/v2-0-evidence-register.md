# 华邦财务中心 V2.0 证据登记册

> 最后核实：2026-07-29（北京时间）。本登记册只陈述带有环境和时间的证据；不以设计、本地测试、部署到磁盘或生产验收互相替代。

## Phase 0 已核实事实

| 项目 | 已核实事实 | 环境与时间 | 证据层级 | Gate 影响 |
| --- | --- | --- | --- | --- |
| 本地实施工作树 | `D:\huabang\worktrees\kingdee-finance-local`，分支 `feature/huabang-full-finance-center`，HEAD `035a4cd`，开始核验时干净 | 本地，2026-07-29 | 本地只读 | 可继续本地实现 |
| 本地迁移图 | `a4e7b1c3d6f8` 是唯一 head；实现计划中不得预写未来 revision ID | 本地，2026-07-29 | 本地只读 | 新迁移必须从当天实际图生成 |
| 生产仓库 | `/srv/huabang-ai-center`，分支 `feature/huabang-ai-mvp`，HEAD `1cdafd03674081ad3620ae7d723cf280774f3d0b`，核验时无工作树改动输出 | 生产只读，2026-07-29 | 生产只读 | V2 本地代码尚未部署 |
| 生产后端 | `huabang-backend.service` 为 active/running；以 `xiaohu` 身份在 `127.0.0.1:8000` 运行 Uvicorn，工作目录为 `/srv/huabang-ai-center/backend` | 生产只读，2026-07-29 | 生产只读 | 未授权前不得重启 |
| 生产迁移状态 | Alembic 单一 head/current 均为 `6c1e4a7d2f09` | 生产只读，2026-07-29 | 生产只读 | 发布前必须重新核实并比较本地迁移链 |
| 旧财务正式写入口 | 生产 OpenAPI 中现有 `/api/v1/finance-center/kingdee/import`、`/vouchers`、`/vouchers/{id}/post`、`/reverse`、`/revise-entries`，以及旧 `/api/v1/finance/*` 写接口 | 生产只读，2026-07-29 | 生产运行时 | 只读验收期不得关闭或代理这些入口 |
| 金蝶源快照 | `ods.kingdee_import_batch=3`、`ods.kingdee_voucher=339`、`ods.kingdee_voucher_entry=4596`、`ods.kingdee_account=416`、`ods.kingdee_balance=6868`；3 个批次均保存备份/manifest 哈希、预期计数与校验结果 | 生产只读，2026-07-29 | 生产只读 | V2 历史导入必须另建 `fin_history` 暂存—校验—发布链，绝不改写 ODS |
| 金蝶覆盖范围 | 凭证日期为 2025-10-31 至 2026-06-30，来自 3 个 source database | 生产只读，2026-07-29 | 生产只读 | 当前账启用日与 2026-07-01 后连续性尚未获得财务确认 |
| 既有正式账 | 旧 `fin` schema 存在 10 个账簿、349 张凭证和 4,617 条分录；它与 V2 的 `fin_current`/`fin_history` 隔离模型不是同一已验收实现 | 生产只读，2026-07-29 | 生产只读 | 不得把旧表直接宣布为 V2 正式账 |
| 数据库角色 | 仅观测到 `huabang` 与 `postgres`；应用使用的 `huabang` 是 `fin` owner，拥有写与 trigger 权限；未发现 `fin_current`、`fin_history`、`fin_read` schema 或分离的 migrator/importer/auditor 角色 | 生产只读，2026-07-29 | 生产只读 | **生产迁移、历史发布和当前账开写 No-Go** |
| 备份与恢复 | 每日备份 cron 存在，但最近可见数据库备份工件为 2026-07-20；没有本轮恢复副本或 PITR 演练证据。备份脚本含明文数据库凭据，凭据值不记录在本文档 | 生产只读，2026-07-29 | 生产只读 | **RPO≤24h/RTO≤4h 未证明，生产开写 No-Go** |
| 后端 V2 定向测试 | 在临时非生产 `APP_SECRET_KEY`/`DB_PASSWORD`/`JWT_SECRET_KEY` 环境变量下，11 个 `test_finance_v2*.py` 文件共 27 项通过 | 本地，2026-07-29 | 本地测试 | 可继续实现；不是数据库恢复或生产验收 |
| 前端基线 | `npm run type-check` 与 `npm run build` 均退出成功；构建输出包含现有依赖的 Vite/Rollup 警告 | 本地，2026-07-29 | 本地构建 | 不等同于浏览器或生产验收 |

## 待确认或不可满足项

| 项目 | 状态 | 所需证据/处置 | 对发布的影响 |
| --- | --- | --- | --- |
| 会计政策签字 | 待财务负责人签字 | 见 `v2-0-accounting-policy-signoff.md` | 没有签字时只能调查和只读准备，不能声明法定报表或正式切换 |
| 当前账起始日与覆盖缺口 | 待确认 | 确认历史截止日、旧系统最终余额、启用日期与任何 `coverage_gap` | 不得批准最终期初或打开 V2 制单 |
| 数据库最小权限 | 不满足 | 由有 `CREATEROLE`/schema 管理权的管理员创建并验证 owner、migrator、app、history importer、readonly auditor | 不得迁移、发布历史或开写 |
| 凭据轮换 | 不满足 | 轮换已暴露于备份脚本的数据库凭据，迁移为受限凭据来源，复核备份作业 | 生产发布与开写 No-Go |
| 备份恢复演练 | 未验证 | 新鲜备份、隔离恢复副本、恢复时间、校验和、PITR 能力和清理记录 | 只读发布可评审；正式开写 No-Go |
| 性能、告警与浏览器验收 | 未开始 | 按实施计划 Phase 5.5A/5.6 在生产形态环境取得证据 | 正式切换与开写 No-Go |

## 当前 Go / No-Go

- 本地 TDD、迁移设计和只读生产调查：**Go**。
- 生产数据库迁移、任何历史写入、服务重启、旧入口冻结、V2 制单/审核/人工过账：**No-Go**。
- 解除 No-Go 的最小顺序：财务口径签字 → 数据库角色与凭据轮换 → 新鲜备份和恢复演练 → 单一 head/恢复副本迁移 → 生产只读验收 → 最终切换 Gate。
