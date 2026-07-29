# 抖音颜色分析 v3.1 Task 0 证据

日期：2026-07-29（Asia/Shanghai）
状态：`DONE_WITH_CONCERNS`

## 范围与边界

本记录只覆盖 v3.1 Task 0 的生产预检、契约冻结复核和既有最小垂直闭环回归。
执行工作树为 `/home/xiaohu/worktrees/huabang-douyin-outfit-task1`，分支为
`task1/douyin-outfit-foundations`。没有开始 Task 1--7；没有修改
`/srv/huabang-ai-center` 运行代码、没有部署或重启服务。

既有完整的三视频脱敏曲线、48/46/2 历史夹具、gzip--测试 API--raw/normalized
SQLite 垂直闭环及 Chrome 只读追溯证据保存在
`docs/plans/douyin-outfit-analytics-task0-evidence.md`。该文件的第 0 节记录本次
生产复核的详细命令结果；本文件是 v3.1 计划指定的评审入口。

## 当前生产复核

| 项目 | 结果 |
| --- | --- |
| 生产工作树 | `/srv/huabang-ai-center`，`feature/huabang-ai-mvp`，干净 |
| 生产 commit | `1cdafd03674081ad3620ae7d723cf280774f3d0b` |
| 隔离工作树（复核时） | `900b97f468aaf3131457e3c61c976faae992e21d`，包含生产 commit |
| PostgreSQL | 16.14，`server_version_num=160014` |
| Alembic | production current/head 均为 `6c1e4a7d2f09` |
| Chrome 目录 API | 已登录同源 `/web/api/creator/item/list`：HTTP 200、业务码 0、10 条、`has_more=true`；仅记录脱敏摘要 |
| 备份完整性 | `huabang_ai_20260729_095234_task0_manual.sql.gz` 通过 `gzip -t`，0600，65,280,707 bytes，SHA-256 `2086c1d428dda9e9588e286cdc5dda05c90e37de84a58ab12e4d57c45de61839` |

没有保存 query、Cookie、token、签名 URL 或数据库密码。

## 回归结果

- 生产 Python 3.12 venv、凭据仅在子进程环境注入：
  `python -m pytest tests/test_douyin_outfit_task0_vertical_loop.py -q`
  -> `13 passed in 0.98s`。
- 相关既有回归：
  `pytest tests/test_life_data_models.py tests/test_life_data_api.py tests/test_life_data_service.py -q`
  -> `103 passed, 1 failed`。失败是现有固定历史 Alembic head
  `2b0f6a7b8c94` 与真实 `6c1e4a7d2f09` 不一致；Task 0 未越界修复。

## 恢复演练阻塞

唯一允许的恢复目标为 `huabang_ai_task0_restore`。应用数据库角色创建它时得到
`ERROR: permission denied to create database`。`sudo -n -l` 和
`sudo -n -u postgres psql -d postgres -Atqc 'SELECT current_user'` 也都返回
`sudo: a password is required`。随后只读确认该恢复库不存在。

未创建或删除任何数据库，未变更权限，也未对生产 `huabang_ai` 写入。备份压缩
完整性已验证，但恢复可用性尚未实证。需要受控 PostgreSQL 管理入口预建唯一
临时库或提供一次性 CREATEDB 能力后，才能执行恢复、结构/样本行数校验和删除。

## 评审结论

Task 0 的契约与最小垂直闭环证据均可评审，生产只读复核也已完成；但恢复演练
门禁未通过，因此只能标记为 `DONE_WITH_CONCERNS`，不可描述为已上线、已完成
迁移准备或已验证恢复。Task 1--7 保持未开始。
