# 华邦财务中心 V2.0 发布基线

> 建立时间：2026-07-29（北京时间）。每次生产部署、迁移、恢复副本演练与切换前必须重新采集，而不是复用本文件中的 revision 或提交。

## 代码与运行时基线

| 位置 | 事实 | 状态 |
| --- | --- | --- |
| 本地工作树 | `feature/huabang-full-finance-center` / `035a4cd` | 已核实，本地未发布 |
| 本地 Alembic | 单一 head `4f7ee5989a97`；新增凭证明细借贷不可同时为正约束及凭证编号 counter/reservation 审计表 | 已核实，尚未在恢复副本或生产执行 |
| 生产仓库 | `feature/huabang-ai-mvp` / `1cdafd03674081ad3620ae7d723cf280774f3d0b` | 已核实，未部署 V2 本地分支 |
| 生产 Alembic | 单一 head/current `6c1e4a7d2f09` | 已核实，发布前须再次执行 `alembic heads --verbose` 与 `alembic current --verbose` |
| 生产运行方式 | `huabang-backend.service` → Uvicorn `app.main:app`，监听 `127.0.0.1:8000`，Nginx active | 已核实；只有 Gate 全通过后才允许重启 |
| 本地后端验证 | V2 定向测试与角色核验 34 passed（临时非生产配置） | 已核实 |
| 本地前端验证 | 类型检查与 Vite 构建成功 | 已核实 |

## 回滚基线与限制

1. 真实 V2 当前账写入发生前，只有在冻结窗口内、已演练的恢复流程可用时才可恢复备份。
2. 真实 V2 当前账写入发生后，业务问题只能前向修复；数据库灾难才按已验证 PITR/备份恢复流程，并重放和核对 RPO 范围内交易。
3. 当前生产备份工件与恢复演练证据不足，不能把本表视为可执行回滚授权。
4. 旧 `/api/v1/finance/*` 与 `/api/v1/finance-center/*` 写入口在 V2 只读验收期保持原状；最终切换前不得关闭。
