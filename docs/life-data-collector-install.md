# LifeData 采集器安装与运维

本文用于华邦指定账号的 LifeData（生意经）浏览器采集器安装、日常值守、故障恢复和验收。

当前版本只允许采集主体账号 `1798826701211732`。不要在其他主体账号下尝试采集，也不要修改脚本绕过账号校验。采集结果只会生成待人工确认的草稿任务，不会自动投放广告。

## 1. 安装前准备

- 使用 Chrome 或 Edge，并安装、启用 Tampermonkey。若浏览器或 Tampermonkey 提示需要“允许用户脚本”或开发者模式，按扩展提示开启。
- 确认能够正常登录 `https://www.life-data.cn/`，且当前主体是 `1798826701211732`。
- 向系统管理员领取一次性传递的采集令牌。令牌属于敏感信息，不要发到群聊、工单、截图、文档或日志中。
- 后端必须已配置令牌的 SHA-256 哈希；后端 `.env` 不保存原始令牌。

## 2. 安装脚本

1. 在已安装 Tampermonkey 的浏览器中打开：
   [https://hbreare.com/life-data-collector.user.js](https://hbreare.com/life-data-collector.user.js)
2. Tampermonkey 弹出安装页后，确认脚本名称为“华邦 LifeData 主动采集器”，点击“安装”。已安装旧版时点击“更新”或重新安装。
3. 打开 Tampermonkey 管理面板，确认该脚本处于启用状态，匹配站点为 `https://www.life-data.cn/*`。
4. 登录生意经。首次弹出“请输入华邦 LifeData 采集令牌”时，只粘贴管理员单独交付的原始令牌并确认一次。脚本会把令牌保存在当前浏览器的 Tampermonkey 脚本存储中。
5. 如果首次提示被取消，可点击浏览器工具栏中的 Tampermonkey 图标，选择“配置/更换采集令牌”重新输入。

## 3. 首次学习模板和 114 条验收

脚本不能凭空构造生意经请求；首次使用或登录恢复后，必须先让页面成功发出一次真实请求以学习模板。

1. 在生意经内切换到主体账号 `1798826701211732`。
2. 打开“视频分析”页，确认地址路径包含 `/flow/content/analysis/video`。
3. 在该页面刷新一次，等待列表正常显示。刷新用于捕获会话头和成功的视频分析请求模板，不能跳过。
4. 保持这个标签页在线并维持登录。脚本学到新模板后会自动尝试采集；也可在右下角浮层点击“立即采集”。首次学习是唯一例外：脚本尚未观察到真实成功请求前，定时器不能凭空采集，必须由操作人打开相应页面并触发一次正常查询。
5. 本次验收总数为 114 条时，脚本会自动请求两页：第 1 页 100 条，第 2 页 14 条，不需要人工翻页。
6. 验收浮层应显示：
   - `主体账号` 为 `1798826701211732`；
   - `标签状态` 为“主标签”；
   - `视频数` 为 `114`；
   - `最近上传`有最新时间；
   - `队列数`为 `0`；
   - `错误`为“无”。
7. 再按“后端、数据库和任务检查”完成服务器侧核对。浮层正确不等于数据库一定已经落库。
8. 为尽可能覆盖生意经业务数据，首次验收后依次打开当前账号有权限的“经营、流量、商品、人群、投放”等页面，并在每页触发一次正常查询。脚本只会学习两个白名单业务接口的成功 JSON；不会猜测账号无权限的请求。学到的非视频模板由主标签每 60 分钟重放一次。

“尽可能采集”取决于当前账号权限和实际打开过的页面。新增模块上线后，至少打开一次该页面，让脚本学习真实请求模板。

### 3.1 缺字段学习闭环

采集器和中台按以下闭环补齐字段，不会猜测接口或从页面文字补数：

1. 采集器检查生意经成功接口返回的完整 JSON，并把真实字段映射为标准字段名。
2. 对每个成功请求模板，采集器只记录其 endpoint、请求参数和能够提供的标准字段；响应正文不会保存到模板注册表。
3. 右下角浮层的 `缺少字段` 最多显示五个优先字段。`spend_fen`、`verified_gmv_fen`、`stat_date` 三个必需采集字段始终排在可选维度前，不会被五项上限隐藏；可选缺口单独标为“可选维度待补”。
4. 操作人按提示进入对应页面并刷新，确保页面正常发出一次成功业务请求。脚本不会自动跳转，也不会调用不存在的服务端重放接口。
5. 浏览器观察到成功响应后学习模板能力，并按既有采集流程把脱敏后的业务请求/响应上传到 `/life-data/ingest`。
6. 中台从已保存的原始采集重新核验字段覆盖；下一次读取 `/life-data-analysis/overview` 时，相应字段会从 `missing` 变为可用，并显示真实页面路径、接口和统计周期来源。

中台契约把原始采集要求和派生分析要求分开：`required_fields` 固定为 `spend_fen`、`verified_gmv_fen`、`stat_date`；`required_analysis_fields` 固定为 `attribution_quality`。当归因状态仍为 `missing` 时，`attribution_quality` 会列入 `missing_analysis_fields`；得到诚实的 `period_estimate` 或 `exact` 后才列入 `available_analysis_fields`。浮层“必需字段已覆盖”只表示三个原始字段已经学到，不代表归因已达到 `exact`，也不代表所有可选维度已齐全。

常见提示页如下：

| 缺少字段 | 打开并刷新的生意经页面 |
| --- | --- |
| 播放量、视频指标 | 流量 → 视频分析 |
| 消耗、广告订单 | 投放 → 广告分析 |
| 支付、核销、退款 | 经营 → 经营概览 |
| 年龄、性别 | 人群分析 |
| 地域 | 地域分析 |
| 小时趋势 | 时间趋势 |
| 视频与订单直接关联标识 | 视频详情 → 交易明细 |

页面刷新后仍显示缺字段时，先确认该账号有页面权限、页面查询成功且浮层“最近上传”已更新；不要从页面表格手工抄数，也不要自行拼接口或补零。

## 4. 浮层状态说明

| 字段 | 含义 | 处理建议 |
| --- | --- | --- |
| 主体账号 | 脚本允许采集的固定主体 | 必须是 `1798826701211732` |
| 标签状态 | “主标签”负责定时采集和重试；“待命标签”不重复采集 | 日常只需保持一个主标签在线 |
| 最近采集 | 最近捕获或主动采集业务响应的时间 | 长时间不更新时先检查登录和模板 |
| 最近上传 | 最近一次成功上传到华邦后端的时间 | 有采集但无上传时检查令牌、网络和后端 |
| 视频数 | 最近一次完整视频采集返回的总数 | 本次验收应为 114 |
| 下次视频采集 | 下一轮视频采集的本地时间 | 正常为每 5 分钟一轮 |
| 下次核心采集 | 下一轮经营、广告和其他核心模板采集的本地时间 | 正常为每 60 分钟一轮 |
| 本轮模板 | 本轮核心采集选中数/跳过数 | 脚本会用最少模板覆盖目标字段 |
| 失效模板 | 因登录或鉴权失效而停用的模板数 | 大于 0 时重新登录并刷新对应页面 |
| 队列数 | 当前浏览器本地等待重传的事件数 | 大于 0 时不要卸载或清队列 |
| 队列排空预计 | 按当前每分钟 40 条或降速后的 20 条计算的预计排空时间 | 仅为当前速率估算，持续失败时会变化 |
| 缺少字段 | 当前建议所需但尚未从成功接口 JSON 中学到的标准字段，最多显示五项及一个页面指引 | 打开提示的生意经页面并刷新一次，等待最近上传更新 |
| 错误 | 最近一次错误或异常提示 | 先按提示恢复，不要反复点击采集 |

浮层可以用右上角 `—` 收起，用 `+` 展开。多个 LifeData 标签同时打开时，脚本只选一个主标签；其他标签显示“待命标签”。主标签关闭后，其他标签通常会在约 30 秒内接管。

## 5. 日常运行和浏览器限制

- 始终保持至少一个已登录的 `www.life-data.cn` 标签页在线，建议保留“视频分析”页。
- 主标签每 5 分钟采集一次视频，已学到的经营、广告和其他核心业务模板每 60 分钟重放；每 60 秒向 AI 中台发送一次不含会话信息的在线心跳。不要通过多开标签提高频率。
- 核心模板按经营、广告、其他分阶段执行；阶段内最多 3 个 LifeData 请求并行并至少错开 1 秒启动。离线队列最多同时上传 2 条，正常速率上限为每分钟 40 条；连续 429 后降为每分钟 20 条，冷却后成功一次才恢复。
- 中台连续 15 分钟未收到心跳会把采集器标记为 `offline`。它能发现浏览器、电脑或脚本已离线，但不能在离线期间替浏览器调用 LifeData。
- 浏览器关闭、电脑关机或休眠、网络断开时，用户脚本不能运行，也不能采集新数据。
- 浏览器重新打开后，只能补采生意经平台当时仍允许查询的数据；平台已经不可查询的历史数据无法由脚本补回。
- 上传失败的事件会进入 Tampermonkey 隔离的 GM 存储并自动退避重试。队列按事件逐记录保存，元数据不包含响应正文；它不是 IndexedDB。队列上限为 500 条或 50 MiB，达到高水位后自动采集暂停，降到 300 条以下才恢复，且不会为腾空间删除已有重试事件。

## 6. 登录失效恢复

1. 先停止反复点击“立即采集”，重新登录 `https://www.life-data.cn/`。
2. 确认登录账号正确，并切换到主体 `1798826701211732`。出现“主体账号不匹配”或“登录账号不匹配”时不得绕过。
3. 重新打开“视频分析”页并刷新一次，等列表成功显示，让脚本重新学习有效模板和会话头。
4. 确认一个标签变为“主标签”。若仍为“待命标签”，检查是否有另一个 LifeData 标签在线，或等待原租约约 30 秒过期。
5. 点击“立即采集”，检查“最近上传”更新、队列逐步回到 0、错误恢复为“无”。
6. 若页面本身也无法加载数据，先处理 LifeData 登录或平台故障；不要清队列、改账号或修改脚本。

## 7. 更换令牌

后端当前只接受一个令牌哈希，更换时由系统管理员统一协调。

1. 管理员生成新的高强度令牌，只把 SHA-256 哈希写入后端配置，原始令牌只向指定使用人单独交付一次；不得把原始令牌写入 `.env`、Git、日志或本文档。
2. 后端新哈希生效后，在浏览器点击 Tampermonkey 图标，选择“配置/更换采集令牌”，输入新令牌。
3. 保持主标签在线，点击“立即采集”，确认“最近上传”更新且队列回到 0。
4. 旧令牌在后端切换哈希后立即失效。若队列增加，先核对切换顺序和后端状态，不要直接清队列。

## 8. 清队列和卸载

### 清空离线队列

清队列会永久丢弃尚未上传的数据，只能在负责人确认这些事件可以放弃后操作。

1. 打开 Tampermonkey 管理面板，进入“华邦 LifeData 主动采集器”的详情。
2. 当前版本使用 Tampermonkey 隔离 GM 存储按事件逐记录保存队列，并维护 `lifeDataQueue:meta`、`lifeDataQueue:pending` 等事务元数据；不要按旧版说明查找 IndexedDB 或只改一个 `lifeDataQueue` 数组。由维护人员确认后，通过受控清理工具删除该脚本的队列逐记录键和对应元数据。
3. 刷新 LifeData 页面，确认浮层“队列数”为 0。
4. 不要误删 `lifeDataCollectorToken` 和 `lifeDataTemplates`；否则需要重新输入令牌并重新打开视频分析页刷新学习模板。

部分 Tampermonkey 版本不显示脚本存储页。此时不要在网页控制台猜测或执行不明代码；如确需彻底清空，按下面的卸载步骤删除脚本及其关联数据，再重新安装。

### 卸载

1. 正常停用前先确认“队列数”为 0，且“最近上传”有最新时间。
2. 在 Tampermonkey 管理面板删除“华邦 LifeData 主动采集器”；如界面询问是否删除关联存储，选择删除。
3. 关闭残留的 LifeData 标签。卸载后浏览器不再采集或补传。
4. 再次安装时需要重新输入令牌，并打开视频分析页刷新学习模板。

## 9. 后端、数据库和任务检查

以下检查只读，不包含部署、迁移、重启或数据修改。需要变更时按正式发布流程另行执行。

### 9.1 后端状态和日志

```bash
sudo systemctl is-active huabang-backend.service
curl -fsS https://hbreare.com/health
sudo journalctl -u huabang-backend.service --since "30 minutes ago" --no-pager
```

服务应为 `active`，健康检查应成功。日志中应能看到“生意经采集完成”及对应 `event_id`、账号、视频数和任务数，且没有连续的 `401`、`403`、`413`、Traceback 或数据库错误。

### 9.2 数据库状态和 114 条数据

在数据库主机上使用批准的只读账号连接；本机采用 PostgreSQL 默认运维方式时可进入：

```bash
sudo -u postgres psql -d huabang_ai
```

查看采集器最近到达和最近成功时间：

```sql
SELECT account_id, status, last_seen_at, last_success_at,
       last_event_id, queue_depth, last_error_at, last_error, updated_at
FROM app.life_data_collector_state
WHERE account_id = '1798826701211732';
```

正常在线时 `last_seen_at` 应约每分钟更新；超过 15 分钟会变为 `status='offline'`。`queue_depth` 是浏览器最近一次上报的队列快照，浏览器浮层“队列数”仍是当前本地待重传数量。

核对最近统计周期的去重视频数：

```sql
SELECT stat_start, stat_end,
       count(DISTINCT item_id) AS distinct_videos,
       max(captured_at) AS latest_capture
FROM app.life_data_video_snapshot
WHERE account_id = '1798826701211732'
GROUP BY stat_start, stat_end
ORDER BY stat_end DESC, stat_start DESC
LIMIT 5;
```

本次真实账号验收的目标行应显示 `distinct_videos = 114`。这 114 条由浏览器自动分两页获取（100 + 14）。

核对原始业务 JSON 没有会话或鉴权键：

```sql
SELECT count(*) AS sensitive_payload_rows
FROM app.life_data_capture
WHERE account_id = '1798826701211732'
  AND concat(request_payload::text, response_payload::text) ~*
      '"(cookie|set-cookie|authorization|x-tt-ls-session-id|root-life-account-id|life-account-id)"[[:space:]]*:';
```

预期 `sensitive_payload_rows = 0`。

### 9.3 阈值任务

```sql
SELECT e.item_id, e.play_count, e.rule_code,
       t.task_no, t.status, t.requires_human_confirm, t.confirmed_at
FROM app.life_data_alert_event AS e
LEFT JOIN app.app_action_task AS t ON t.id = e.task_id
WHERE e.account_id = '1798826701211732'
ORDER BY e.triggered_at DESC
LIMIT 20;
```

达到自然播放阈值的视频应只产生一条 `rule_code='natural_play_2000'` 预警及一条 `source_type='life_data_rule'` 任务。新任务必须是 `status='draft'`、`requires_human_confirm=true`，未经人工确认不得投放。

本次 34,310 播放视频的去重验收可执行：

```sql
SELECT e.item_id,
       count(DISTINCT e.id) AS alert_count,
       count(DISTINCT t.id) AS task_count,
       max(t.status) AS task_status,
       bool_and(t.requires_human_confirm) AS human_confirm_required
FROM app.life_data_alert_event AS e
LEFT JOIN app.app_action_task AS t ON t.id = e.task_id
WHERE e.account_id = '1798826701211732'
  AND e.play_count = 34310
GROUP BY e.item_id;
```

预期目标视频为 `alert_count = 1`、`task_count = 1`、`task_status = 'draft'`、`human_confirm_required = true`。立即再次采集后这些计数仍应保持 1。

## 10. 安全边界

- 只覆盖主体账号 `1798826701211732`；账号不匹配时脚本和后端都会拒绝。
- 业务指标唯一来源是抖音来客生意经成功接口返回的 JSON；页面 DOM、可见表格文字和人工抄录都不是指标来源。
- 浏览器只观察并重放 `https://www.life-data.cn` 下 `/api/dito/query` 和 `/api/lowcode_api/query` 两个白名单接口。
- LifeData 会话头只在当前 Tampermonkey 脚本存储中用于已登录会话重放；上传前会过滤 `cookie`、`authorization`、`x-tt-ls-session-id`、`root-life-account-id`、`life-account-id` 等敏感键。
- Cookie、Authorization、会话令牌、动态签名和签名密钥不得离开浏览器；字段能力注册表不得保存响应正文或上述敏感信息。
- `/life-data/ingest` 只接收浏览器已采集并脱敏的数据，不是服务端重放入口；`/life-data/status` 只接收采集状态，`/life-data-analysis/overview` 只提供认证后的只读分析。
- 缺失值必须保持 `missing`；同期但无直接平台关联键的数据只能标记为 `period_estimate`；只有平台直接关联键充分时才能标记为 `exact`。不得猜测、补零或把间接关系升级为精确归因。
- 原始采集令牌只保存在指定浏览器的 Tampermonkey 存储中并作为 `X-Collector-Token` 发送；后端只保存 SHA-256 哈希，不记录原始令牌。
- 单次上传大小上限为 2,000,000 字节；遇到超限不得临时放宽或拆改脚本，应交由维护人员确认数据范围。
- 本地队列只用于网络失败重传，不是长期备份。清队列、清浏览器资料或卸载扩展都会造成未上传事件丢失。
- 阈值命中只创建待人工确认的草稿任务；系统不会自动创建或修改投放计划、预算、暂停或上传动作，也不得把草稿视为已批准动作。
