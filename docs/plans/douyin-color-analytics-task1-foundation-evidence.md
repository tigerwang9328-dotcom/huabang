# 抖音颜色分析 Task 1 模型与迁移证据（v3.1）

日期：2026-07-30（Asia/Shanghai）

## 范围与边界

- 本记录只覆盖 v3.1 的“账号隔离、状态机、持久模型和迁移”。每个视频片段最多关联一件 `clear_primary` 主要衣物；没有穿搭、多件归因、对比组或拍摄条件模型。
- 所有抖音业务表位于 `douyin` schema，且除账号根表外均显式保存 `account_id`。跨账号关系使用复合外键，不能通过间接 join 推断账号。
- `garment_colors` 同时具备 `(account_id, style_id, id)` 唯一键；片段、video-color 指标和报告均以 `(account_id, style_id, color_id)` 引用该键，禁止同账号内把颜色错配给另一款号。`collection_batch_parts` 同时具备 `(account_id, batch_id, id)` 唯一键；采集项以三列外键引用，禁止同账号跨批次混用分片。
- 创作者账号在库中只保存 `expected_creator_fingerprint`；上传时的原始 creator ID 仅在请求内做哈希比对。模型、迁移和本记录不保存 Cookie、令牌、签名 URL、query/fragment 或平台响应正文。
- 迁移挂在既有全局 Alembic 链，revision `2d7c4a9e8b10`、down revision `1fdf4577d7d8`。仓库中不存在第二条 `alembic_douyin` 链；`alembic heads` 的结果为一个 head。
- `huabang_douyin_migrator` 只拥有 `douyin` schema 的迁移权限；没有向 `fin_current` 或 `fin_history` 授权。生产应用库和服务尚未迁移、部署或重启。

## 红绿验证

1. 红灯：新增状态/窗口/分片边界约束测试后，`test_v31_database_constraints_cover_all_frozen_state_sets_and_static_bounds` 因缺少 `ck_douyin_snapshot_analysis_type` 失败。
2. 绿灯：补齐模型、Pydantic 枚举和静态迁移 DDL 后，`pytest tests/test_douyin_color_models.py -q` 通过 `6 passed`（仅现有 Pydantic/pytest 配置弃用警告）。
3. 合并结构验证：`alembic heads` 输出唯一 `2d7c4a9e8b10 (head)`；迁移文件完成 Python 编译。
4. 真实 PostgreSQL：从已验证的独立恢复库克隆 `huabang_douyin_task1_global_verify_20260730`，先执行 upgrade，再以 SQL 验证：
   - 第二个 active 账号被部分唯一索引拒绝；
   - 跨账号颜色外键被拒绝；
   - 相同账号重复款号、重复 SKU 被拒绝；
   - `part_number=0`、`analysis_type=99`、非法 `clear_primary` 组合和非法计算任务状态被检查约束拒绝；
   - 同账号内“款号 A + 属于款号 B 的颜色”及“批次 A + 属于批次 B 的分片”均被三列外键拒绝；
   - 两条不同采集项可引用同一个去重快照；
   - 相同报告键的第二个 current revision 被部分唯一索引拒绝。
   演练输出为 `revision=2d7c4a9e8b10`、`douyin_tables=19`、owner=`huabang_douyin_migrator`。
5. 仅在上述临时库执行 downgrade，输出 `downgraded_revision=1fdf4577d7d8`、`downgraded_douyin_tables=0`。退出处理删除了临时库；生产不使用 downgrade 作为回滚手段。
6. 空库验证：完整历史全链从 revision zero 回放会在早于本任务的 `d2e3f4a5b6c7` 迁移因缺少 `dim.dim_store` 失败，临时库已清理。这是既有全链可重放性问题，不能伪称本任务修复。对一个全新临时数据库执行 bootstrap、`stamp 1fdf4577d7d8` 后升级本迁移，输出 `revision=2d7c4a9e8b10`、`douyin_tables=19`；这证明本迁移自身可在空 schema 上创建全部新表。

## Task 1 尚待合入前的检查

- 完整后端回归（2026-07-30）最终为 `813 passed, 1 skipped, 6 failed`。6 项失败均为本变更前存在的 Finance/AI 失败；`test_life_data_migration_has_one_resolvable_head` 是本次单一 head 导致的陈旧断言，已更新并与 Task 0/Task 1 相关回归共同通过 `29 passed`。后续仍须单独修复并复跑那 6 项既有失败。
- 生产应用数据库尚处旧 revision，直接运行 `alembic check` 预期返回 `Target database is not up to date`；升级后又会暴露既有 Finance/ODS/Sys autogenerate 漂移，因此不能作为本模块绿色门禁，也不能通过无关 schema 改动或扩大权限来掩盖。
- 完成独立规格复审，确认没有 Critical/High/Medium 问题后再提交并进入 Task 2。
