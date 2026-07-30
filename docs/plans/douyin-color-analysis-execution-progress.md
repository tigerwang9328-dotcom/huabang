# 抖音颜色分析 v3.1 执行进度

## 运行边界

- 实现工作树：`/home/xiaohu/worktrees/huabang-douyin-color-v31`
- 生产运行目录：`/srv/huabang-ai-center`（只读预检；发布阶段另行记录）
- 规格：`docs/plans/douyin-color-analysis-direct-launch-plan-v3.1.md`
- 状态：进行中

## Task 0

- 状态：PASSED（独立审查结论：PASS）
- 当前证据：`douyin-color-analytics-task0-evidence.md` 记录 v3.1 专属、未注册的颜色分析契约 POC：令牌上下文账号归属、创作者核对、跨账号引用、快照/采集项关系、gzip 分片、原始/归一曲线分层、只读 trace 和分片完成协议。旧 `douyin_outfit_task0` v3.2 穿搭 POC 只保留为历史资料，不能作为 v3.1 Task 0 合约证据。生产在执行中被其他财务发布推进到 `f52273fb160268376b428ff6b56c1d42297f91f5` / Alembic `1fdf4577d7d8`，因此已从该提交新建隔离工作树；生产目录的未跟踪财务发布文件未被改动。三条已打开作品的同源 `analysis_type=1/7` 接口均成功返回逐点曲线（112、32、89 点）；`analysis_type=7` 仍严格保持平台跳出曲线值语义和报告关闭状态。v3.1 专属 48/46/2 脱敏夹具、SHA-256 与递归敏感工件负向扫描均已提交并通过 8 项契约测试。唯一登录创作者仅以不可逆指纹预配置在 root 0600、功能关闭的清单中；当前前端静态基线没有账号创建入口。先前应用角色生成的手工 gzip 备份恢复后少了 24 张财务表，已被独立审查拒绝且不再作为证据。已启用的 `huabang-postgres-backup.timer` 随后成功生成 PostgreSQL 专用全库备份；恢复到 `huabang_ai_task0_restore` 后，所有者为 `huabang`、Alembic 为 `1fdf4577d7d8`、全部非系统表为 200 且逐 schema 与源库一致，`sys.sys_user=7`、`dwd.dwd_pos_ticket=1955`，SHA-256 旁车校验通过。当前应用角色的 `alembic check` 受既有财务 schema 权限隔离阻断，Task 1 必须使用独立迁移角色或结构副本。未修改生产运行代码、未重启或部署；恢复库保留供审阅。

## 后续任务

- Task 1：PASSED（提交 `3d73805`、`21ea490`；模型、复合外键、迁移、统一审计写入服务与 PostgreSQL 持久任务基础已在隔离分支完成并经独立审查。）
- Task 2：PASSED。生产 schema 版本副本 `e951b2d0a6c4` 经 Douyin migration 与显式 merge 到 `3a2d7e951b2c`；聚焦回归 `45 passed, 1 warning`。真实 PostgreSQL/ASGI 验收和最终独立复审均已通过，无未解决 Critical、High、Medium 或 Low 问题；可进入 Task 3，未部署且阶段 A 未开启。
- Task 3：未开始
- Task 4：未开始
- Task 5：未开始
- Task 6：未开始
- Task 7：未开始

## 生产阶段

- A：未开始
- B：未开始
- C：未开始
- D：未开始

## 验收前迁移与数据库门槛（历史，2026-07-30）
以下为验收前检查记录；真实验收结果以 Task 2 证据文档顶部的 2026-07-30 结构副本、merge 和 ASGI 记录为准。

- 只读预检时生产运行目录当前 commit 为 `a52a679894d6e533d87efcb3d79e81b43f696793`；隔离工作树的 Alembic 单一 head 为 `2d7c4a9e8b10`。
- 使用应用角色对生产库运行 `alembic current`/`alembic check` 均报告 `Can't locate revision identified by 'e951b2d0a6c4'`。未执行迁移、stamp、downgrade 或任何生产写入。
- 应用角色 `huabang` 的 `rolcreatedb=false`；现有隔离恢复库 `huabang_ai_task0_restore` 未包含 `douyin.collection_batches` 或 `douyin.collection_items`。因此不能安全地以生产库或恢复库代替 Task 2 的真实 PostgreSQL 集成/并发测试。
- 下一步必须由具备建库权限的迁移角色提供一次性独立临时数据库（建议 `huabang_ai_douyin_task2_test`），从当前隔离工作树执行迁移后运行并发、过期提交、跨账号令牌和快照/采集项幂等测试；完成后立即删除该临时库并记录结果。
