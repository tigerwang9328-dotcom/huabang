# backend/app/modules/dingtalk — 钉钉 Stream 入站消费

<!-- agentmap:generated:start -->
## 范围

钉钉 Stream 入站事件消费,**独立进程运行**(systemd `huabang-dingtalk-stream.service`),不接入 FastAPI lifespan。收事件 → dispatcher 落库 → 快速 ACK;含审批/考勤/员工/财务/HR 同步。**不负责**:FastAPI 路由内调用、出站推送(在 `services/dingtalk.py` + `jobs/push_jobs`)。

## 关键文件

- `runner.py` — 进程入口,`python -m app.modules.dingtalk.runner`,构建 client 并 `start()`
- `stream_client.py` — `DingtalkEventHandler`(继承 `EventHandler`),收事件组装 payload → `dispatcher.dispatch_event` → `AckMessage.STATUS_OK`;`build_client()` 凭证校验
- `dispatcher.py` — 按 topic 分发到 sync/* 落库
- `repository.py` — DB 写入封装
- `attendance_sync.py` — 考勤同步(独立辅助)
- `sync/` 子包:
  - `runner.py` — sync 总调度
  - `_common.py` — 公共工具
  - `approvals.py` — 审批同步
  - `attendance.py` — 考勤同步
  - `employees.py` — 员工同步
  - `finance_parser.py` — 财务事件解析
  - `hr_parser.py` — HR 事件解析

## 本地状态与失败行为

- 凭证缺失:`build_client` 抛 `RuntimeError`(不打印密钥值)
- 事件处理异常:handler 内捕获 + 落日志,**仍返回 STATUS_OK** 防重投
- 连接超时:钉钉每 12 小时发 disconnect,client 自动重连(见 systemd 日志)
- 多实例:重复消费 + 争抢 Stream 连接,**禁止多实例**

## 公共输入/输出

- 入参:钉钉 Stream `EventMessage`(headers + data)
- 出参:`AckMessage.STATUS_OK` + 落库(`dingtalk_event` 原始档 + 业务表)
- 凭证:`settings.DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET`(AppKey/AppSecret)

## 模块不变量

1. **只允许一个实例运行**(systemd 单例);多实例重复消费争抢连接。
2. **EventHandler 必须 STATUS_OK 快速 ACK**,失败也 ACK 防重投;异常在 handler 内捕获并落日志。
3. 凭证来自 `.env`;缺凭证抛错但**不打印密钥值**。
4. 事件先落 `dingtalk_event` 原始档,再由 `sync/*` 解析入业务表;**幂等键防止重复处理**。
5. 凭证变更必须重启 `huabang-dingtalk-stream.service`。

## 焦点测试/构建命令

```bash
# 服务状态
systemctl status huabang-dingtalk-stream.service --no-pager

# 测试
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_finance_parser.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

服务文件:`deploy/systemd/huabang-dingtalk-stream.service`,以 xiaohu 身份运行,`WorkingDirectory=/srv/huabang-ai-center/backend`,`ExecStart=.venv/bin/python -m app.modules.dingtalk.runner`。重启:`sudo systemctl restart huabang-dingtalk-stream.service`。出站钉钉推送走 `services/dingtalk.py` + `jobs/push_jobs.py`,与本模块无关。
