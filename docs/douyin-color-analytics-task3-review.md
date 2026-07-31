# Task 3 采集可靠性审查（进行中）

审查范围：`tools/douyin-color-analytics-collector.user.js`、`tools/douyin-color-collector/`、对应 Node 测试，以及 `collector-config` 后端契约。

## 已核对通过

- 控制面返回并由脚本验证 schema、最低版本、显式启用、分片上限、队列上限和并发/间隔参数；最大解压分片为 5 MiB，分片记录数为 50，本地上限为 100 批/500 MiB。
- `collection_enabled` 不再硬编码为启用，改由 `DOUYIN_COLOR_COLLECTION_ENABLED` 显式控制且默认关闭；对应 RED/GREEN 测试已证明关闭时脚本配置不会启用采集。
- 油猴只有 `hbreare.com` 一个 `@connect`；未发现持久化令牌、Cookie、签名 URL、query/hash 或硬编码凭据。
- 浏览器运行时令牌只存在 `runtimeConfig` 内存；IndexedDB 队列写入前执行递归敏感键剔除。
- 目录和曲线观察在真实登录创作者页验证；切换到流量分析后页面内存观察计数从 0 变为 1。
- 真实浏览器切换到任务创建的空白页再返回作品页时，页面事件探针记录到 `hidden` 与 `visible`（各两次）；此前的超时是探针等待单位误用，非页面未派发事件。
- Node 回归：12 passed；后端安全与接收回归：28 passed；`node --check` 与 `git diff --check` 通过。

## 未通过的真实验收门槛（阻止批准）

- 未在安全验收接收环境使用短期采集令牌验证 401/403 停止、服务端拒绝、缺片补传/finalize 和 80% 队列保护。
- 未完成真实系统休眠、断网恢复、账号切换和 Chrome 重启场景。
- 因上述外部验收未完成，Task 3 审查结论为 **REQUEST CHANGES**，不得提交为完成或进入 Task 4。

## 回归命令

```text
PYTHONPATH=. /srv/huabang-ai-center/backend/.venv/bin/python -m pytest \
  tests/test_douyin_color_security.py tests/test_douyin_color_ingest.py -q
node --check tools/douyin-color-analytics-collector.user.js
node --test tests/douyin-color-collector/*.test.cjs
git diff --check
```
