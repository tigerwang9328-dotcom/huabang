# 抖音颜色分析 v3.1 Task 0 证据

日期：2026-07-29（Asia/Shanghai）
状态：`REVIEW_PENDING`

## 范围与边界

本记录只覆盖 v3.1 Task 0 的生产预检、契约冻结复核和 v3.1 专属的最小合约证明。
执行工作树为 `/home/xiaohu/worktrees/huabang-douyin-color-v31`，分支为
`task1/douyin-color-v31-foundations`。它以当前生产提交重新建立，并迁入了仅限
Task 0 的合约证明；没有开始 Task 1--7；没有修改
`/srv/huabang-ai-center` 运行代码、没有部署或重启服务。

旧 `douyin_outfit_task0` 是 v3.2 穿搭 POC。其三视频脱敏曲线、48/46/2 历史夹具、
gzip--测试 API--raw/normalized SQLite 垂直闭环及 Chrome 只读追溯资料仍保存在
`docs/plans/douyin-outfit-analytics-task0-evidence.md`，但它不是、也不得再被描述为
v3.1 颜色分析的合约证据。本文件是 v3.1 计划指定的评审入口。

## 当前生产复核

| 项目 | 结果 |
| --- | --- |
| 生产工作树 | `/srv/huabang-ai-center`，detached `HEAD`；发现财务发布留下的未跟踪文件，未改动 |
| 生产 commit | `f52273fb160268376b428ff6b56c1d42297f91f5` |
| 隔离工作树（复核时） | 基于上述生产 commit 的 `task1/douyin-color-v31-foundations` |
| PostgreSQL | 16.14，`server_version_num=160014` |
| Alembic | production current/head 均为 `1fdf4577d7d8` |
| Chrome 目录 API | 已登录同源 `/web/api/creator/item/list`：HTTP 200、业务码 0、10 条、`has_more=true`；仅记录脱敏摘要 |
| 自动备份 | `huabang-postgres-backup.timer` 为 `enabled`/`active`；2026-07-29 12:52 UTC 的专用 PostgreSQL 服务成功退出，生成 `/var/backups/huabang-postgres/huabang_ai_20260729T125202Z.dump` 及 SHA-256 旁车文件 |

没有保存 query、Cookie、token、签名 URL 或数据库密码。

## v3.1 专属合约证明

- 独立文件：`backend/app/poc/douyin_color_analysis_task0_contract.py` 与
  `backend/tests/test_douyin_color_analysis_task0_contract_v31.py`。两者不导入、
  不改名或复用旧 `douyin_outfit_task0` POC，且没有注册到生产路由、模型或迁移。
- 红灯：先只有新测试时，导入
  `app.poc.douyin_color_analysis_task0_contract` 失败：
  `ModuleNotFoundError`；随后才实现最小 POC。
- 绿灯覆盖：上传账号只从 Bearer 令牌上下文获取并拒绝客户端 `account_id`；
  `observed_creator_id` 不匹配被拒绝；跨账号款号/颜色引用被拒绝；
  `video_analysis_snapshots` 的非 NULL 去重关系与
  `collection_items(snapshot_id)` 的多对一引用得到验证；同一分片内两条
  `raw_record_hash IS NULL` 失败项均可保存，符合 SQLite/PostgreSQL UNIQUE 的
  NULL 语义；分片乱序、同内容重试、内容冲突、`part_count` 冲突、缺片查询、
  未齐全 finalize 失败和按分片号排序的服务器端 `batch_hash` 均得到验证。
- 垂直闭环追加证明：v3.1 POC 的 `/parts` 只接受
  `Content-Encoding: gzip`；白名单化原始曲线保存为 `raw_response_json`，独立
  `normalized_curve_json` 保存为 `0..1` 曲线，原始 JSON 未被数值转换覆盖；
  只读 trace 页面仅显示作品 ID、已记录原始证据和归一曲线，不显示令牌、URL 或
  query/hash。该闭环是未注册 POC 的 Task 0 证据，不是生产 API。

## 既有回归结果（非 v3.1 合约证据）

- 旧 v3.2 穿搭 POC 的生产 Python 3.12 venv 回归（仅历史资料，非本 Task 0
  v3.1 合约证据）：
  `python -m pytest tests/test_douyin_outfit_task0_vertical_loop.py -q`
  -> `13 passed in 0.98s`。
- 相关既有回归：
  `pytest tests/test_life_data_models.py tests/test_life_data_api.py tests/test_life_data_service.py -q`
  -> `103 passed, 1 failed`。失败是现有固定历史 Alembic head
  `2b0f6a7b8c94` 与真实 `6c1e4a7d2f09` 不一致；Task 0 未越界修复。

## 恢复演练

第一次手工 gzip 备份恢复后只得到 170 张业务表，缺少生产中的
`fin_current` 与 `fin_history` 表；独立审查据此拒绝了“完整结构”结论。该发现
已保留为审计事实，旧手工备份不再作为恢复门禁证据。

最终恢复只使用已启用的 `huabang-postgres-backup.timer` 产物。该服务由
PostgreSQL OS 账户运行 `pg_dump -Fc --no-owner --no-privileges`，不使用应用
数据库凭据；备份文件及旁车校验和均为 0600，`sha256sum -c` 通过。唯一恢复目标
为 `huabang_ai_task0_restore`：先精确删除同名临时库（若存在），再创建归属
`huabang` 的独立库，使用 `pg_restore --exit-on-error --no-owner --no-privileges`
恢复。生产 `huabang_ai` 未被恢复、写入或删除。

恢复后以 `postgres` 只读验证得到：

| 校验项 | 结果 |
| --- | --- |
| 恢复库/所有者 | `huabang_ai_task0_restore` / `huabang` |
| Alembic revision | `1fdf4577d7d8`（与生产 current/head 一致） |
| 非系统 schema 表数 | 200（与源库一致） |
| `sys.sys_user` | 7 行 |
| `dwd.dwd_pos_ticket` | 1,955 行 |
| 每 schema 结构抽样 | `ai=5`、`app=27`、`backup=2`、`dim=14`、`dm=13`、`dwd=17`、`dws=8`、`fin=26`、`fin_current=19`、`fin_history=5`、`fin_read=3`、`log=11`、`ods=27`、`public=8`、`sys=15`；均与源库一致 |
| 自动备份校验 | SHA-256 旁车校验通过；服务退出码 `0/SUCCESS` |

以上证明已启用的自动备份可被 PostgreSQL 工具完整恢复为与源库一致的结构，并包含
可读取的业务样本。恢复库保留供本次门禁审阅；它是唯一临时库，不是生产库，也没
有应用部署、重启或迁移。

## 评审结论

v3.1 专属合约证明、当前生产复核及自动备份恢复演练均已记录，等待重新运行合约
测试及独立审查。旧 v3.2 穿搭 POC 不计入本结论；旧不完整的手工备份也不计入。
即使审查通过，结论也只表示 Task 1 可以开始，不表示模块已上线、已部署、已完成
迁移或已完成生产验收。Task 1--7 保持未开始。
