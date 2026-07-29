# 抖音颜色分析 v3.1 Task 0 证据

日期：2026-07-29（Asia/Shanghai）
状态：`PASSED`

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

## 三视频同源曲线抽样

在用户已登录且已打开的三个不同作品详情页中，只读取现有同源资源并以页面会话内的
相同请求复取响应；未保存或输出原始 URL、query、Cookie、token 或签名。三个页面
均观察到目录接口和
`/janus/douyin/creator/data/realtime/analysis/data_center`，两种分析类型都返回
`status_code=0`，响应结构均为：

```text
analysis_trend.current_item[] / analysis_trend.similar_author[]
point = { key: "mm:ss", value: number }
```

脱敏逐点摘要为：

| 作品指纹 | `analysis_type=1` | `analysis_type=7` |
| --- | --- | --- |
| A | 112 点，首点 `00:00=1` | 112 点，首点 `00:00=0.1081` |
| B | 32 点，首点 `00:00=1`，末点 `00:31=0.04` | 32 点，首点 `00:00=0.2`，末点 `00:31=0.04` |
| C | 89 点，首点 `00:00=1`，末点 `01:28=0.0167` | 89 点，首点 `00:00=0.1667`，末点 `01:28=0.0167` |

页面可见“留存分析”和“跳出分析”入口；`analysis_type=1` 的首点与页面留存曲线的
100% 起点一致。由于尚未把三视频的跳出图逐点人工截图对照固化为夹具，
`analysis_type=7` 仍仅命名为 `platform_bounce_curve_value`，并保持报告开关关闭，
不得标为跳出率或参与排名。

## 单真实账号预配置

目录接口的当前页目录项只有一个 `user_id`，其原值只在浏览器内用于计算
`SHA-256("douyin-color-v31-creator-fingerprint:" + user_id)`；记录的预期创作者
指纹为 `6a89363b783fa2d435dc56a63f64d5cc4df59f71f69c5857c41da2e7adf12d2a`，没有
保存原始 ID。由于 Task 1 的账号表尚未创建，受控主机上已经准备了 inert 的
`/etc/huabang/douyin-color-analytics-preprod.conf`：`root:root`、0600，账户别名为
`primary`、状态为 `preconfigured`，且 `DOUYIN_COLOR_FEATURE_ENABLED=false`。文件
不含 Cookie、token、原始创作者 ID 或签名请求；Task 1 的账号 bootstrap 必须显式
读取该指纹才可启用，不能在当前阶段自行启用。

当前隔离工作树的 `frontend/src` 共扫描 87 个 Vue/TypeScript 文件，未发现
“新增账号”“账号管理”或抖音账号创建入口；首期运营页面因此没有可自行新增账号的
路径。该结论是当前未部署模块的静态基线证据，不代表 Task 4/7 前端已完成。

## v3.1 历史夹具

`backend/tests/fixtures/douyin/historical-20260728.sanitized.json` 及其 SHA-256
旁车文件已作为 v3.1 专属夹具提交。它由已脱敏的原始 48 条采集资料机械重封装，
schema 版本为 `douyin-color-v3.1-task0-fixture-v1`，并在测试中固定验证：48 个
目录项、46 条视频、2 条跳过项、64 位作品 ID 字符串、空曲线、HTTP 429、非零
业务错误、相同重复快照记录和 SHA-256。

夹具包含递归安全扫描器及刻意污染的负向样本，拒绝敏感键
`token/cookie/password/signature/captcha/query/url/hash/authorization`（唯一允许的
业务去重键为 `source_snapshot_hash`），并拒绝 URL、Cookie、Bearer、`msToken`、
`a_bogus` 等敏感值。夹具没有这些会话或签名内容。

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

## 当前基线测试与迁移权限

- 在重新基线后的工作树中，用生产同版本虚拟环境并将 `PYTHONPATH` 指向隔离工作树
  执行 `pytest tests/test_douyin_color_analysis_task0_contract_v31.py -q`，结果为
  `8 passed in 0.76s`。旧 v3.2 垂直环测试文件已不在当前生产基线，不能作为本次
  v3.1 回归命令。
- `alembic heads` 与 `alembic current` 均为 `1fdf4577d7d8`。`alembic check`
  使用现有应用数据库角色时稳定失败于 `permission denied for schema fin_current`：
  当前应用角色 `huabang` 不属于具有该 schema 权限的 `fin_app` 角色。该权限隔离
  属于当前财务发布，未在本任务中扩大权限。Task 1 的迁移验证必须使用独立、最小
  权限的迁移运行角色或结构副本管理连接；不能把应用角色检查失败伪装成通过，也不
  得为此给应用角色授予财务 schema 权限。

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

独立审查在提交 `99d6239` 后给出 `PASS`。v3.1 专属合约证明、当前生产复核、
三视频接口抽样、历史夹具、单账号预配置和自动备份恢复演练均已通过；旧 v3.2
穿搭 POC 与旧不完整手工备份均不计入结论。跳出语义逐点截图夹具仍使
`analysis_type=7` 保持为平台跳出曲线值、报告开关关闭；Task 1 的迁移验证也必须
使用独立运行角色或结构副本。Task 0 通过只表示 Task 1 可以开始，不表示模块已
上线、已部署、已完成迁移或已完成生产验收。
