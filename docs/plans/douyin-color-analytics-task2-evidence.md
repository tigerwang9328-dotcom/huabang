# 抖音颜色分析 v3.1 Task 2 证据与剩余门槛

状态：PASSED。真实 PostgreSQL/ASGI 验收与最终独立复审均已通过；可进入 Task 3，仍不得部署或开启 A 阶段开关。

## 2026-07-30 真实隔离验收

- 临时库 huabang_ai_douyin_task2_test_20260730d 仅恢复生产 schema，未复制业务数据；schema dump SHA-256：a49b367a8bd3cc098a5fc803d8bb4568830c0a52c23e6b69535c359702c654dd。
- 以真实生产 revision e951b2d0a6c4 和无 DDL merge revision 3a2d7e951b2c 迁移成功；未写生产 huabang_ai。
- 真实 FastAPI/ASGI 并发验收及聚焦回归通过：45 passed, 1 warning。
- alembic check 仍报告既有全局模型漂移，只保留为诊断，未称为全绿。
- 空库直接回放仍受既有 dim.dim_store 初始 DDL 缺失阻塞；已记录为全局迁移债务，不伪造 revision。


## 已实现并经过聚焦回归的边界

- 上传只接受 gzip，并分别限制压缩体 1 MiB、解压体 4 MiB；请求体以流读取而不是先整体加载。
- 上传令牌只以 SHA-256 哈希查找账号；作品 ID 保持字符串；创作者 ID 只以冻结的域分离指纹比对。
- 负载递归拒绝敏感键、内联敏感赋值、签名 URL、query/hash 和客户端 `account_id`；标题、消息、观察账号名及管理员显示字段会清洗后保存。
- 原始响应使用字段白名单保存曲线和数值状态，服务端对该白名单内容自行计算快照哈希；客户端声明的 `source_snapshot_hash` 不会写入快照标识。
- 批次、分片、视频、快照、采集项和心跳首次写入使用 PostgreSQL `ON CONFLICT DO NOTHING ... RETURNING`，随后由唯一键读取胜出行。重复采集项不再累加批次统计。
- 支持乱序分片、缺片查询、显式 finalize、24 小时 receiving 状态过期并以正常 409 响应提交状态；健康状态采用上海时区预期在线窗口。
- 账号、令牌和预期时段管理仅通过 `douyin.admin` 后端路由开放；没有新增账号管理前端入口。

## TDD 与回归记录

- 先后新增并观察到失败：服务器自算快照哈希、原始响应白名单/计数、采集健康机器字段白名单；相应测试在实现前分别因缺失导入或未校验输入失败。
- 聚焦命令：`PYTHONPATH=. /srv/huabang-ai-center/backend/.venv/bin/python -m pytest tests/test_douyin_color_security.py tests/test_douyin_color_ingest.py -q`。
- merge 前聚焦结果：`27 passed, 1 warning`。该 warning 来自既有 Pydantic class-based config，不是本模块行为失败。
- 回归命令：`pytest tests/test_douyin_color_models.py tests/test_douyin_color_foundations.py tests/test_douyin_color_security.py tests/test_douyin_color_ingest.py -q`。
- merge 前回归结果：`42 passed, 1 warning`；当时 `alembic heads` 为单一 `2d7c4a9e8b10`。真实结构副本验收后的 head 为 `3a2d7e951b2c`，完整聚焦结果为 `45 passed, 1 warning`。

## 独立代码复审

- 两轮独立复审后，Task 2 当前代码无未解决 Critical 或 High：第二轮确认 `CollectionItem` 幂等与仅新增项计数、健康元数据机器标识白名单和持久化文本净化已落实。
- 原复审 Medium“尚无安全测试库”已由 2026-07-30 的临时结构副本、真实迁移和 ASGI 验收解除；最终复审确认文档事实一致，Task 2 无未解决 Critical、High、Medium 或 Low 问题，允许进入 Task 3。

## 接受前的历史阻塞（已解除）
以下内容为真实验收前的阻塞记录，已由本文件顶部的 2026-07-30 证据解除；保留它仅用于可追溯性。

验收前没有可安全使用的临时 PostgreSQL 库。生产库 Alembic revision 与隔离工作树不一致，且应用角色无法建库；禁止把生产 `huabang_ai` 或 Task 0 恢复库用作写入测试目标。

2026-07-30 的只读预检确认应用角色 `huabang` 的 `rolcreatedb=false`，并且 `sudo -n -u postgres psql` 返回“需要密码”；未尝试密码、未创建数据库、未修改生产库。

验收前取得独立临时库后必须以 FastAPI/真实 PostgreSQL 验证：

1. 两个并发相同 part 与同一 part 内重复 record 返回幂等结果且计数只增加一次；两个不同 part 并发写入相同快照均成功接收，且每个分析类型只保存一份快照；
2. `expired` 409 的状态实际提交；
3. 账号 A 令牌无法读取或写入账号 B 的批次、视频和快照；
4. 24 小时过期、缺片 finalize、part hash 冲突、重复快照引用和敏感值拒绝；
5. 临时库执行迁移、`alembic current` 与 `alembic check`，并保留脱敏输出。

上述门槛的真实验收与最终独立复审均已通过；可以进入 Task 3。

## 已准备的临时库验收工件

- `backend/tests/integration/test_douyin_color_task2_postgres.py`：使用 ASGI `httpx` 客户端、真实 active account、存储的令牌哈希和 Bearer 请求覆盖并发同 part、同 part 重复记录、两个不同分片并发写入同一视频/曲线时的快照去重、原子计数和 expired 409 提交。仅当 `DOUYIN_TASK2_POSTGRES_ACCEPTANCE=1` 时执行，普通回归会明确跳过。
- `backend/scripts/run_douyin_color_task2_postgres_acceptance.sh`：只接受以 `huabang_ai_douyin_task2_test` 开头的数据库名，清除 `ALEMBIC_DATABASE_URL` 覆盖并分别核验应用配置/psql 实际目标后，核验迁移后 revision、运行 check 和上述验收；不创建或删除任何数据库。现有全库 `alembic check` 漂移会原样输出为诊断但不会阻断 Task 2 真实验收，最终证据必须单独列出该诊断，不得把它写为迁移全绿。
- 已验证脚本语法和测试模块编译；在当前没有临时库的环境中验收测试按预期显示 `1 skipped`，这不是通过结果。
