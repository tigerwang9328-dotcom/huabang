# 抖音自有服装同款颜色表现分析系统 Implementation Plan v3.1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在华邦 AI Center 内交付可直接上线、可长期运行、可追溯和可恢复的“油猴采集器 + FastAPI 服务 + Vue 运营后台”模块，通过人工标注每个片段的一件主要分析衣物，比较同款不同颜色视频的留存表现，并在平台跳出曲线语义验证通过后有条件开放跳出指标。

**Architecture:** 已登录的抖音创作者中心页面只负责同源学习和限速采集，油猴仅上传白名单业务字段；服务端负责账号校验、批次分片幂等、原始证据保存、归一化、主要衣物标注、异步计算、报告快照、权限与审计。底层所有商品、采集、标注、指标和报告数据均按抖音账号隔离，首期只配置并启用一个真实账号；生产功能通过 shadow、标注试运行、报告只读灰度和正式运营四阶段开关逐级开放。

**Tech Stack:** Tampermonkey/JavaScript、IndexedDB、`GM_xmlhttpRequest`、FastAPI、SQLAlchemy、Alembic、PostgreSQL、Vue、现有华邦 AI Center 鉴权/审计/部署体系。

## Global Constraints

- 这是一个完整生产版本。Task 0～7 和上线阻塞清单全部通过前，不得把模块描述为已上线或对全部运营开放。
- 已验证生产源码结构为 `/srv/huabang-ai-center/backend/app/api/v1`、`backend/app/models`、`backend/app/services`、`backend/alembic/versions`、`frontend/src/api`、`frontend/src/views` 和 `frontend/src/router/index.ts`；Task 0 必须再次以实际生产提交为准。
- 底层数据模型、复合外键、上传令牌和抖音账号匹配支持多个账号；首期生产只允许一个 `active` 真实账号，运营后台不提供新增账号入口，后续账号只能由管理员配置。
- 目录接口为 `GET /web/api/creator/item/list`；留存与平台跳出曲线接口为 `GET /janus/douyin/creator/data/realtime/analysis/data_center`，分别使用 `analysis_type=1` 和 `analysis_type=7`。
- 64 位作品 ID 从浏览器到数据库、日志、导出和前端一律按字符串处理。
- 当前页面会话内可临时持有包含签名参数的真实 URL 以同源重放；原始 URL、query、hash、Cookie、token、`msToken`、`a_bogus`、验证码和签名不得写入源码、IndexedDB、日志、导出、服务器请求或数据库。
- 采集器只上传字段白名单。服务器再次递归扫描敏感键和值；命中后拒绝负载并只记录脱敏错误分类。
- 所有 worker 共用一个全局发起调度器，任意两个脚本主动请求的开始时间至少间隔 1000ms；最多两个在途请求，不能用 worker 数绕过全局限速。
- 429 最多重试 5 次，退避为 `min(60s, 2^attempt × 1000ms) + 0～500ms` 抖动；同一视频同一分析类型每批最多失败 5 次，之后进入失败项，不得永久占用队列。
- 只有创作者中心目标页面保持打开且登录账号匹配时才采集。关闭页面、浏览器休眠、登录过期或账号切换都会暂停，不承诺 24 小时无人值守。
- `raw_response_json` 保存白名单化但未经数值转换的接口证据；`normalized_curve_json` 保存 `0..1` 曲线。指标只能使用归一化层，且必须可追溯到原始层。
- `analysis_type=7` 在三条真实视频逐点验收完成前只能显示为 `platform_bounce_curve_value`，不得标为“跳出率”或参与排名。
- 留存与平台跳出独立选取快照、独立计算、独立计数。跳出失败或语义拒绝不得排除留存样本。
- 每个片段最多指定一件主要分析衣物。只有 `focus_status=clear_primary` 且标注已批准的片段参加颜色排名；`multi_focus` 和 `unclear` 只进入质量计数。
- 一段曲线不得同时分摊给多件衣物；同一主要衣物在视频内多次出现可建多个片段，最终仍聚合成一个 video-color 视频样本。
- 报告只比较同一账号、同一款号、同一观察窗口和同一可选位置段的颜色；禁止把 T+2、T+7、T+30 和临时采集混在一个排名中。
- 所有报告显示有效样本数、排除的多重点/无法判断片段数、样本门槛、出现位置、视频等权口径、可用时的曝光加权参考、数据截止时间、算法版本、账号、观察窗口和关联性说明。
- 平均留存排名至少 3 条不同视频；稳定性排名至少 5 条不同视频，使用样本标准差 `n - 1`。2～4 条可展示标准差但不得进入稳定性排名。
- 数据库迁移前先备份。回滚优先关闭功能开关、吊销令牌和回滚应用版本，保留新表，不默认执行破坏数据的 Alembic downgrade。
- 每个任务必须按 TDD 执行：先写失败测试并保存失败证据，再实现，再运行针对性测试和相关回归，最后提交；不得跨任务合并未经评审的生产变更。

---

## 1. 生产交付范围与阶段门禁

### 1.1 最终生产能力

全部完成后系统必须支持：

1. 底层多抖音账号隔离、上传令牌绑定和浏览器实际账号核对；首期只启用一个真实账号；
2. 目录分页、T+2/T+7/T+30 重采、失败补采、限速、休眠恢复和本地队列保护；
3. 分片乱序接收、幂等重试、缺片查询、显式完成、超时过期和完整失败明细；
4. 原始证据、归一曲线、目录快照、播放量和来源字段的版本化存储；
5. 款号、颜色、尺码 SKU、主要分析衣物片段标注、提交审核、重叠审批和操作审计；
6. 留存与跳出独立计算、主要衣物资格过滤、出现位置分层、观察窗口隔离、异步重算和可复现报告；
7. 健康状态、预期在线时段、版本漂移、队列容量、告警、导出、备份和恢复。

### 1.2 四阶段生产开关

| 阶段 | 开关 | 可见范围 | 放行条件 |
| --- | --- | --- | --- |
| A 采集 shadow | `collector_upload_enabled=true`，其余关闭 | 管理员、审计员 | 三视频真实闭环、账号匹配、批次完成协议和敏感字段扫描通过 |
| B 标注试运行 | `annotation_enabled=true` | 1 名指定运营、审核员 | 双窗口标注、审核、版本冲突和历史样本试标通过 |
| C 报告只读灰度 | `report_enabled=true`，`export_enabled` 按权限 | 管理员、分析员 | 留存手算、重算、样本门槛、报告复现和数据说明通过 |
| D 正式运营 | 授权范围全部开启 | 全部授权角色 | 备份恢复、令牌轮换、失败注入、回滚和生产真实批次通过 |

`bounce_report_enabled` 独立于上述阶段，只有语义状态为 `verified_lower_is_better` 或 `verified_higher_is_better` 才能打开。

每阶段必须形成评审记录。任何阶段失败只回退对应功能开关，不删除已采集证据。

## 2. 冻结的数据模型

### 2.1 抖音账号、令牌和采集实例

```text
douyin_creator_accounts(
  id, account_key, display_name,
  expected_creator_id, expected_account_name,
  status, created_at, updated_at,
  UNIQUE(account_key),
  UNIQUE(expected_creator_id)
)

douyin_upload_tokens(
  id, account_id, token_hash, token_prefix,
  status, last_used_at, expires_at_nullable,
  created_by, created_at, revoked_by_nullable, revoked_at_nullable,
  UNIQUE(token_hash)
)

collector_instances(
  id, account_id, installation_id, script_version, schema_version,
  last_heartbeat_at, last_success_at, current_status,
  current_page_path_nullable, current_page_type_nullable,
  document_visibility_nullable, observed_creator_id_nullable,
  observed_account_name_nullable, queued_batch_count, queued_bytes,
  last_error_category_nullable, created_at, updated_at,
  UNIQUE(account_id, installation_id)
)

collector_expected_schedules(
  id, account_id, timezone, weekday_mask,
  expected_start_local, expected_end_local, enabled,
  created_at, updated_at,
  UNIQUE(account_id, weekday_mask, expected_start_local, expected_end_local)
)

collector_events(
  id, account_id, installation_id, event_type, occurred_at,
  error_category_nullable, endpoint_name_nullable,
  http_status_nullable, business_status_code_nullable,
  retry_count_nullable, sanitized_message_nullable
)
```

首期配置固定为 `DOUYIN_COLOR_MAX_ACTIVE_ACCOUNTS=1`。底层表和查询不写死单账号；管理员 API 可以创建非 active 配置，但尝试启用第二个账号时返回 HTTP 409 `first_release_single_active_account`。运营前端不提供账号新增或启用入口。

`current_page_path` 只允许 `/creator-micro/...` 形式的 pathname；不得含 `?` 或 `#`。`sanitized_message` 最长 500 字符，只允许预定义错误消息模板，不接受任意响应正文或 JSON。

采集器健康状态固定为：

```text
online_active
online_hidden
suspended
auth_required
upload_blocked
offline_expected
offline_unexpected
```

状态推导规则：

- 最近 5 分钟有心跳且页面可见：`online_active`；
- 最近 5 分钟有心跳但 `document.visibilityState=hidden`：`online_hidden`；
- 心跳主动报告浏览器恢复、系统唤醒或定时器漂移超过 2 分钟：`suspended`，下次稳定心跳恢复；
- 401/403 或页面账号不可识别：`auth_required`；
- API 不可达、令牌拒绝、队列达到 80% 或服务器禁采：`upload_blocked`；
- 无心跳但不在账号配置的预期在线时段：`offline_expected`；
- 预期在线时段内超过 10 分钟无心跳：`offline_unexpected` 并告警。

默认预期在线时段为 Asia/Shanghai 每天 09:00～18:00，可由管理员按账号修改。5 分钟无心跳只表示状态过期，不直接产生故障告警。

### 2.2 批次、分片、采集项与去重快照

```text
collection_batches(
  id, account_id, client_batch_id, schema_version, script_version,
  source_date_start, source_date_end, created_at_client,
  first_received_at, last_part_received_at, finalized_at_nullable,
  expires_at, part_count, batch_hash_nullable, status,
  item_count, success_count, skipped_count, failure_count,
  observed_creator_id, installation_id,
  UNIQUE(account_id, client_batch_id)
)

collection_batch_parts(
  id, batch_id, part_number, part_hash, record_count,
  uncompressed_bytes, received_at, status,
  UNIQUE(batch_id, part_number),
  UNIQUE(batch_id, part_hash)
)

collection_items(
  id, account_id, batch_id, part_id,
  video_id_string_nullable, analysis_type_nullable,
  item_status, error_category_nullable, endpoint_name_nullable,
  http_status_nullable, business_status_code_nullable,
  sanitized_error_message_nullable, retry_count,
  raw_record_hash_nullable, snapshot_id_nullable,
  created_at,
  UNIQUE(part_id, raw_record_hash)
)

video_analysis_snapshots(
  id, account_id, video_id, analysis_type,
  collected_at, source_snapshot_hash,
  raw_response_json, normalized_curve_json,
  normalization_version, original_value_unit, curve_quality_status,
  similar_author_normalized_curve_json_nullable,
  valley_list_json_nullable, valley_related_items_json_nullable,
  video_age_hours_at_collection, observation_window,
  curve_audience_count_nullable,
  http_status, business_status_code, status_message,
  first_seen_batch_id, created_at,
  UNIQUE(account_id, video_id, analysis_type, source_snapshot_hash)
)
```

关系方向固定为 `collection_items.snapshot_id -> video_analysis_snapshots.id`。相同账号、作品、分析类型和内容 hash 的快照只存一份，后续多个采集项均可引用该快照，不能把 `collection_item_id` 放在去重快照中作为一对一外键。

批次状态固定为：

```text
receiving
completed
completed_with_errors
expired
abandoned
failed
```

分片完成协议：

1. 第一个 `POST /collection-batches/{client_batch_id}/parts` 原子创建 `receiving` 批次并冻结 `account_id`、`part_count`、`schema_version`、`observed_creator_id` 和 `installation_id`；
2. 分片允许乱序；`part_number` 必须为 `1..part_count`；
3. 同一 `part_number`、相同 `part_hash` 重试返回原结果；同一编号不同 hash 返回 HTTP 409 `part_content_conflict`；
4. `part_count` 首次写入后不可修改，冲突返回 HTTP 409 `part_count_conflict`；
5. `GET /collection-batches/{client_batch_id}/missing-parts` 返回缺失编号；
6. 所有分片到齐后客户端调用 `POST /collection-batches/{client_batch_id}/finalize`；服务器重新校验分片、账号、计数和敏感字段后完成事务；
7. `batch_hash = SHA256(part_1_hash + "|" + ... + "|" + part_n_hash)`，按 `part_number` 升序由服务器生成；
8. 全部成功/跳过为 `completed`，至少一项业务失败但批次证据完整为 `completed_with_errors`；
9. 24 小时未完成的 `receiving` 批次转为 `expired`；用户明确放弃为 `abandoned`；结构或安全校验不可恢复为 `failed`；
10. 只有 `completed` 或 `completed_with_errors` 可触发计算；只有这两种完整状态可更新 `collector_instances.last_success_at`。

采集项状态固定为：

```text
pending
success
skipped_non_video
empty_curve
auth_failed
rate_limited
network_failed
http_failed
business_failed
upload_failed
```

### 2.3 视频与目录观测快照

```text
videos(
  id, account_id, video_id_string, title, published_at, duration_ms,
  cover_url_nullable, creator_detail_path, source_type,
  first_collected_at, last_collected_at, collection_status,
  UNIQUE(account_id, video_id_string)
)

video_catalog_snapshots(
  id, account_id, video_id, collected_at,
  play_count_at_collection_nullable,
  traffic_source_json_nullable,
  raw_item_whitelist_json,
  source_snapshot_hash,
  UNIQUE(account_id, video_id, source_snapshot_hash)
)
```

`raw_item_whitelist_json` 只保存经批准的作品 ID、标题、发布时间、时长、封面无签名稳定路径、作品类型、播放量和流量来源字段。若接口不能稳定给出曲线对应受众数，`curve_audience_count` 保持 NULL，禁止用播放量冒充曲线样本人数。

观察窗口按采集时视频年龄确定：

```text
t2:     36 <= video_age_hours_at_collection < 72
t7:    144 <= video_age_hours_at_collection < 216
t30:   672 <= video_age_hours_at_collection < 792
ad_hoc: 其他年龄
```

日常队列每天包含：前天发布、7 天前、30 天前和失败待补采作品。一个快照只能属于一个观察窗口。

### 2.4 商品、SKU 与主要分析衣物标注

```text
garment_styles(
  id, account_id, style_code, style_name, main_image_nullable,
  status, created_at, updated_at,
  UNIQUE(account_id, style_code)
)

garment_colors(
  id, account_id, style_id, color_code, color_name, color_image_nullable,
  status, created_at, updated_at,
  UNIQUE(account_id, style_id, color_code)
)

garment_skus(
  id, account_id, color_id, sku_code, size_name_nullable,
  status, created_at, updated_at,
  UNIQUE(account_id, sku_code)
)

video_clips(
  id, account_id, video_id, style_id_nullable, color_id_nullable,
  start_ms, end_ms, input_start_ms, input_end_ms,
  curve_resolution_ms, focus_status, focus_note_nullable,
  annotation_status,
  overlap_reason_nullable, overlap_status,
  overlap_approved_by_nullable, overlap_approved_at_nullable,
  submitted_by_nullable, submitted_at_nullable,
  approved_by_nullable, approved_at_nullable,
  created_by, created_at, updated_by, updated_at,
  version, deleted_at_nullable
)
```

`style_id` 和 `color_id` 表示当前片段的一件主要分析衣物。数据库字段允许 NULL，但必须满足以下检查：

```text
clear_primary -> style_id 和 color_id 均非 NULL，颜色必须属于该款号，可参加排名
multi_focus   -> style_id 和 color_id 均为 NULL，不参加单件颜色排名
unclear       -> style_id 和 color_id 均为 NULL，不参加单件颜色排名
```

`focus_status` 固定为：

```text
clear_primary
multi_focus
unclear
```

运营判断规则：

- 当前主要展示或讲解一件衣物：`clear_primary`；
- 同时重点展示两件或多件衣物，无法选出唯一主要对象：`multi_focus`；
- 无法判断主要展示对象：`unclear`；
- 视频从上衣重点切换到裤子重点时拆为两个片段；
- 同一款同色后续再次出现可新增片段，最终仍按一个 video-color 视频样本聚合；
- 第一版不记录同屏所有衣物，不做自动识别、搭配关系、组合评分、联合归因或复杂权重。

标注状态固定为：

```text
draft
submitted
approved
rejected
deleted
```

数据库负责账号外键一致、focus/style/color 组合、`start_ms >= 0`、`end_ms > start_ms` 和软删除，其中 focus 检查约束为：

```sql
CHECK (
  (focus_status = 'clear_primary' AND style_id IS NOT NULL AND color_id IS NOT NULL)
  OR
  (focus_status IN ('multi_focus', 'unclear') AND style_id IS NULL AND color_id IS NULL)
);
```

服务层负责 `end_ms <= video.duration_ms`、同账号/同款/同色归属、版本冲突和跨记录重叠。跨色重叠必须审批；只有 `clear_primary + approved + overlap approved/not_required` 的片段进入指标计算。

### 2.5 语义、指标、重算任务与报告

```text
metric_semantic_validations(
  id, account_id, metric_key, semantics_status,
  evidence_video_ids_json, verified_by_nullable, verified_at_nullable,
  notes_nullable, created_at, updated_at,
  UNIQUE(account_id, metric_key)
)

video_color_metrics(
  id, account_id, video_id, style_id, color_id,
  observation_window,
  retention_snapshot_id,
  bounce_snapshot_id_nullable,
  retention_source_hash, bounce_source_hash_nullable,
  annotation_set_hash, metric_input_hash, metric_version,
  average_retention, retention_drop,
  average_platform_bounce_curve_value_nullable,
  max_platform_bounce_curve_value_nullable,
  clip_count, total_clip_duration_ms,
  average_relative_position, earliest_relative_position,
  latest_relative_position, average_clip_duration_ms,
  video_duration_ms, dominant_position_segment,
  retention_calculation_status, bounce_calculation_status,
  calculated_at,
  UNIQUE(
    account_id, video_id, style_id, color_id,
    observation_window, metric_version, metric_input_hash
  )
)

calculation_jobs(
  id, account_id, job_type, target_type, target_id,
  deduplication_key, requested_by, status, attempt_count,
  available_at, lease_owner_nullable, lease_expires_at_nullable,
  started_at_nullable, finished_at_nullable,
  sanitized_error_message_nullable, created_at,
  UNIQUE(deduplication_key)
)

color_performance_snapshots(
  id, account_id, style_id, color_id, as_of_date,
  source_data_cutoff_at, calculation_date,
  observation_window, position_segment, metric_version,
  report_revision, report_input_hash, is_current, report_status,
  retention_video_sample_count, bounce_video_sample_count,
  eligible_video_sample_count,
  excluded_multi_focus_clip_count,
  excluded_unclear_clip_count,
  average_retention, retention_stddev_sample_nullable,
  average_relative_position, average_clip_duration_ms,
  front_segment_sample_count, middle_segment_sample_count,
  rear_segment_sample_count,
  other_colors_equal_weight_retention_nullable,
  other_colors_video_weighted_retention_nullable,
  retention_delta_vs_other_colors_nullable,
  exposure_weighted_retention_reference_nullable,
  average_platform_bounce_curve_value_nullable,
  other_colors_equal_weight_bounce_nullable,
  other_colors_video_weighted_bounce_nullable,
  bounce_delta_vs_other_colors_nullable,
  average_rank_eligible, stability_rank_eligible,
  calculated_at
)
```

报告全部属于当前账号自有历史视频分析，不再存在范围类型或范围 ID。`position_segment` 固定为 `all`、`front`、`middle` 或 `rear`。PostgreSQL 当前报告唯一索引为：

```sql
CREATE UNIQUE INDEX uq_color_report_current
ON color_performance_snapshots (
  account_id, style_id, color_id, as_of_date,
  observation_window, position_segment, metric_version
)
WHERE is_current = TRUE;
```

历史 revision 唯一索引不再包含可空范围字段：

```sql
CREATE UNIQUE INDEX uq_color_report_revision
ON color_performance_snapshots (
  account_id, style_id, color_id, as_of_date,
  observation_window, position_segment,
  metric_version, report_revision
);
```

`annotation_set_hash` 由参与计算的 `clear_primary` 已批准片段 ID、版本、边界、主要款色和审批状态规范化生成；`metric_input_hash` 由 retention snapshot、可选 bounce snapshot、`annotation_set_hash`、观察窗口和算法版本生成。即使留存快照未变，只要跳出快照或标注变化，也能产生新的不可覆盖指标。

同一报告键重算时，在一个事务内把旧行 `is_current` 改为 false，新建 `report_revision + 1`、`is_current=true` 的行。`report_input_hash` 由参与的 video-color metric ID/hash、观察窗口、位置筛选、截止时间和算法版本生成；旧 revision 的业务值和 hash 永不覆盖。

指标状态固定为 `pending`、`computed`、`insufficient_data`、`stale`、`failed`；报告状态固定为 `generating`、`ready`、`stale`、`failed`；计算任务状态固定为 `queued`、`running`、`succeeded`、`retryable_failed`、`terminal_failed`。

新快照、标注新增/修改/删除/恢复、focus 状态变化、重叠审批、算法版本升级或语义状态变化时：

```text
受影响 video-color -> stale
生成幂等 calculation_jobs -> worker 计算
受影响报告 -> stale
指标完成 -> 生成新 color_performance_snapshots
```

Task 0 优先复用生产现有任务队列；若不存在支持持久化、租约和重试的后台队列，则实现 PostgreSQL `FOR UPDATE SKIP LOCKED` 的独立 worker，入口固定为：

```text
python -m app.workers.douyin_color_calculation_worker
```

历史重算不得在 FastAPI 请求线程中执行。

## 3. 冻结的上传、版本和安全契约

### 3.1 分片封包

```json
{
  "schema_version": 1,
  "client_batch_id": "5bc92766-f733-4fc2-9417-af49b810b93d",
  "script_version": "1.0.0",
  "source_date_start": "2026-07-27",
  "source_date_end": "2026-07-27",
  "created_at": "2026-07-29T06:00:00Z",
  "installation_id": "4f13949c-f66e-4685-b0d9-925460ec731b",
  "observed_creator_id": "non-sensitive-platform-account-id",
  "observed_account_name": "display-name",
  "part_number": 1,
  "part_count": 1,
  "part_hash": "sha256-of-canonical-records",
  "records": []
}
```

- 账号归属不接受客户端 `account_id` 或 `account_key`；服务器只从上传令牌解析 `account_id`。
- `observed_creator_id` 必须等于令牌账号的 `expected_creator_id`。不匹配返回 HTTP 409 `creator_account_mismatch`，采集器立即停止批次并要求人工确认。
- 页面检测到账号变化时立即暂停，不再向旧批次追加记录。
- 单分片最多 50 条作品记录，解压后最多 5 MiB，使用 `Content-Type: application/json` 和 `Content-Encoding: gzip`。
- canonical JSON 使用 UTF-8、无多余空白、对象键按 Unicode 代码点排序、数组保持原顺序，64 位 ID 为字符串。`part_hash` 对不含 `part_hash` 自身的规范化分片业务内容计算。
- 浏览器关闭或上传中断后，IndexedDB 保留固定 `client_batch_id`、`part_number`、`part_count`、`part_hash` 和 records；恢复时先查询 missing-parts，再补传并 finalize。

### 3.2 API

```text
GET  /api/v1/douyin-color-analytics/collector-config
POST /api/v1/douyin-color-analytics/collector-heartbeats
POST /api/v1/douyin-color-analytics/collector-events
POST /api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/parts
GET  /api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/missing-parts
POST /api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/finalize
POST /api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/abandon
GET  /api/v1/douyin-color-analytics/collection-batches
GET  /api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/items
GET  /api/v1/douyin-color-analytics/videos
GET  /api/v1/douyin-color-analytics/videos/{video_id}
GET  /api/v1/douyin-color-analytics/videos/{video_id}/snapshots
GET/POST/PATCH /api/v1/douyin-color-analytics/admin/accounts

GET/POST/PATCH /api/v1/douyin-color-analytics/styles
GET/POST/PATCH /api/v1/douyin-color-analytics/styles/{style_id}/colors
GET/POST/PATCH /api/v1/douyin-color-analytics/skus
GET/POST/PATCH/DELETE /api/v1/douyin-color-analytics/video-clips
POST /api/v1/douyin-color-analytics/video-clips/{clip_id}/submit
POST /api/v1/douyin-color-analytics/video-clips/{clip_id}/approve
POST /api/v1/douyin-color-analytics/video-clips/{clip_id}/reject
POST /api/v1/douyin-color-analytics/video-clips/{clip_id}/restore

GET  /api/v1/douyin-color-analytics/styles/{style_id}/color-report
GET  /api/v1/douyin-color-analytics/styles/{style_id}/color-report/export
POST /api/v1/douyin-color-analytics/recalculations
GET  /api/v1/douyin-color-analytics/calculation-jobs
GET  /api/v1/douyin-color-analytics/health
GET  /api/v1/douyin-color-analytics/audit-events
```

报告查询参数固定为：

```text
GET /styles/{style_id}/color-report
  ?observation_window=t7
  &position_segment=all
  &as_of_date=2026-07-29
```

`position_segment` 只允许 `all/front/middle/rear`；不存在分组或拍摄条件查询参数。

`GET /collector-config` 返回：

```json
{
  "minimum_script_version": "1.0.0",
  "recommended_script_version": "1.0.0",
  "supported_schema_versions": [1],
  "collection_enabled": true,
  "max_part_records": 50,
  "max_uncompressed_bytes": 5242880,
  "max_local_batches": 100,
  "max_local_bytes": 524288000,
  "global_start_interval_ms": 1000,
  "max_in_flight_requests": 2
}
```

服务器至少在一个脚本升级周期内同时支持当前和前一个 schema 版本；不支持时返回 `unsupported_schema_version`、`minimum_supported_script_version` 和 `recommended_script_version`，不得部分入库。

### 3.3 本地队列保护

- 默认最多 100 个未完成批次或 500 MiB，以先达到者为准；
- 达到 80% 时停止新采集，显示 `upload_blocked`，允许继续补传已有批次；
- 未上传数据绝不自动删除；
- 控制面板提供“导出未上传批次”“恢复上传”“人工放弃批次”，人工放弃必须二次确认并生成本地审计记录；
- 安装文档明确：清理浏览器站点数据会删除未上传队列，操作前必须导出；
- 成功 finalize 且服务端返回 batch hash 后，本地批次保留 7 天再清理；清理不影响服务器证据。

### 3.4 字段白名单与日志清洗

允许上传的目录字段和曲线字段必须在 `collectorFieldWhitelist.js` 中显式声明。服务器递归拒绝以下大小写不敏感键和值片段：

```text
cookie
token
authorization
mstoken
a_bogus
signature
password
captcha
set-cookie
```

拒绝日志只记录 `sensitive_field_detected`、JSON 路径的脱敏结构和批次 ID，不记录命中原值。事件消息、任务错误和 API 错误统一经过 `sanitize_douyin_text()`，删除 URL query/hash、控制字符和超过 500 字符内容。

### 3.5 权限与审计

权限固定为：

| 权限 | 默认角色 |
| --- | --- |
| `douyin.collector.write` | 采集器令牌，仅心跳、事件、配置和批次接口 |
| `douyin.annotation.edit` | 运营，查看视频和维护草稿/提交标注 |
| `douyin.annotation.approve` | 审核员，审批标注和跨色重叠 |
| `douyin.report.view` | 分析员，只读报告和钻取 |
| `douyin.report.export` | 分析员，经单独授权后导出 |
| `douyin.admin` | 管理员，商品、账号配置、令牌、语义和功能开关 |
| `douyin.audit.read` | 审计员，只读审计日志 |

Task 0 将这些权限映射到现有华邦角色模型，不另造第二套登录系统。SKU 导入、标注修改/删除/恢复、focus 状态变化、重叠审批、语义状态、导出、账号管理员配置、令牌创建/轮换/吊销和功能开关变更必须写审计日志。

CSV/XLSX 导出对以 `= + - @` 开头的文本加前置单引号，使用 UTF-8，明确 Asia/Shanghai 时间、账号、款号、颜色、观察窗口、位置筛选、截止时间、指标版本、样本数和关联性说明。

## 4. 冻结的统计口径

### 4.1 曲线与片段

```text
原始白名单响应
-> normalization_version 归一化
-> 片段指标
-> video_id + style_id + color_id + observation_window
-> 颜色表现快照
```

- 原始数值单位记录为 `ratio_0_1`、`percent_0_100` 或 `unknown`；`unknown` 不得计算；
- 归一曲线固定为 `0..1`，超界、非单调时间、重复时间点冲突或缺关键字段进入 `curve_quality_status`；
- 当前曲线为秒级，标注 UI 使用整秒输入并保存输入值和吸附值；
- 边界到最近可用点超过 1 秒时为 `insufficient_curve_resolution`；
- 等间隔点用算术平均，不等间隔用梯形积分时间加权平均，边界在线性插值后积分；
- 只有 `clear_primary` 且已批准的片段参加计算；`multi_focus` 和 `unclear` 不产生 video-color 指标；
- 同视频同款同色多个合格片段按片段时长聚合为一个 video-color 样本，一段曲线最多计入一件主要衣物。

位置计算：

```text
relative_position = clip_start_ms / video_duration_ms
front  = [0, 1/3)
middle = [1/3, 2/3)
rear   = [2/3, 1]
```

报告至少展示平均留存、平均出现位置、平均片段长度、位置段分布、有效排名视频样本数、排除多重点片段数和排除无法判断片段数，并提供全部/前段/中段/后段筛选，避免把开头优势误解为颜色因果。

质量计数规则：

```text
eligible_video_sample_count
  = 当前账号 + 款号 + 颜色 + 观察窗口 + 位置筛选中，
    至少有一个合格 clear_primary 片段的不同视频数

excluded_multi_focus_clip_count
  = 当前账号 + 观察窗口内 multi_focus 且已提交/批准的片段数

excluded_unclear_clip_count
  = 当前账号 + 观察窗口内 unclear 且已提交/批准的片段数
```

款色报告显示质量计数时，明确标注后两项是当前账号与观察窗口的全局标注质量数据，不伪装成某一颜色的排除数量；视频列表另可按 focus 状态钻取。

### 4.2 独立快照选择

在 `source_data_cutoff_at` 前：

- 留存指标选择同账号、同视频、同观察窗口最新成功且质量合格的 retention snapshot；
- 跳出指标独立选择最新成功且质量合格的 bounce snapshot；
- 没有 bounce snapshot 时留存仍计算，`bounce_snapshot_id=NULL`，`bounce_calculation_status=insufficient_data`；
- 只有账号级语义状态为 `verified_lower_is_better` 或 `verified_higher_is_better` 时才计算和排名跳出；
- 历史重采或标注变化通过新的 `metric_input_hash` 和 `report_revision` 生成新指标/报告快照，不覆盖旧业务值。

### 4.3 基线、加权和样本门槛

颜色 C 的主基线为同账号、同款、同观察窗口、同位置筛选内其他合格颜色平均值的颜色等权平均：

```text
retention_delta_vs_other_colors(C)
  = average_retention(C)
  - equal_weight_mean(其他合格颜色的平均留存)
```

同时展示：

- 视频等权平均：每条 video-color 样本权重相同，回答“每条视频作为一个样本时平均如何”；
- 其他颜色视频加权参考：其他颜色按视频样本数加权；
- 曝光加权参考：仅当每个样本有可靠 `play_count_at_collection` 时展示；它不是曲线受众加权；
- 若无准确曲线受众数，固定提示“平台未提供该曲线对应的准确样本人数，低播放视频的百分比可能波动较大”。

门槛：

```text
展示平均值：至少 2 条不同视频
平均留存排名：至少 3 条不同视频
稳定性排名：至少 5 条不同视频
样本标准差：分母 n - 1
```

留存和跳出分别使用 `retention_video_sample_count`、`bounce_video_sample_count`。无其他合格颜色时差值为 NULL。

### 4.4 跳出语义门控

```text
unverified                -> 只显示 platform_bounce_curve_value 原始/归一曲线
verified_lower_is_better  -> 升序低值榜
verified_higher_is_better -> 降序高值榜
rejected                  -> 隐藏跳出报告
```

三条不同长度、不同表现真实视频必须逐点核对页面时间轴、值、范围和方向，并保存截图/记录和审核人。语义状态变化会使所有相关跳出指标和报告变为 stale 并异步重算，不影响留存。

## 5. 数据保留、备份、恢复与维护

### 5.1 保留周期

```text
原始曲线、归一曲线、目录快照、标注、指标和报告快照：长期保留
采集事件：90 天
普通心跳：30 天；之后只保留按日聚合
失败采集项和失败任务详情：180 天
审计日志：长期保留
导出文件：请求时流式生成，不在服务器长期保存
```

清理任务只删除达到保留期且不影响审计/追溯的事件与心跳明细，先输出待删数量并记录审计事件。

### 5.2 恢复目标

- 数据库每日备份，RPO 不超过 24 小时；
- 内部模块 RTO 不超过 8 小时；
- 每次数据库迁移前生成可验证备份；
- 每季度执行一次恢复演练并记录恢复时长、校验行数和报告 hash；
- 回滚顺序：关闭功能开关 → 吊销采集令牌 → 回滚应用 → 校验旧版本可读新表 → 必要时从备份恢复；
- Alembic downgrade 不作为常规回滚步骤。

### 5.3 固定维护节奏

- 每日：成功批次、待标注、登录状态、不完整批次、重算失败；
- 每周：接口成功率、字段命中率、脚本版本、失败作品和标注抽检；
- 每月：令牌轮换演练、数据库增长、页面/API 抽样、样本覆盖和过期数据清理；
- 上线初期预留每周 2～4 小时开发维护，另计运营标注时间。

## 6. 文件结构与职责

后端：

```text
backend/app/models/douyin_color_analytics.py
  全部模块表、枚举、部分唯一索引和账号外键

backend/app/schemas/douyin_color_analytics.py
  API 请求/响应、状态枚举和字段白名单类型

backend/app/api/v1/douyin_color_analytics.py
  路由、权限依赖和 HTTP 状态映射

backend/app/services/douyin_color_security_service.py
  敏感字段扫描、消息清洗、账号匹配

backend/app/services/douyin_color_ingest_service.py
  分片幂等、missing parts、finalize 和快照去重

backend/app/services/douyin_color_annotation_service.py
  片段校验、版本锁、状态和重叠审批

backend/app/services/douyin_color_curve_service.py
  原始证据归一化、质量判定、插值和积分

backend/app/services/douyin_color_metrics_service.py
  独立快照选择、video-color 指标和 dirty 标记

backend/app/services/douyin_color_report_service.py
  观察窗口、位置筛选、门槛、基线和报告快照

backend/app/services/douyin_color_export_service.py
  CSV/XLSX 公式转义和元数据

backend/app/workers/douyin_color_calculation_worker.py
  独立重算 worker 的 fallback 实现

backend/alembic/versions/20260729_01_douyin_color_analytics.py
  首次生产迁移
```

前端：

```text
frontend/src/api/douyinColorAnalytics.ts
frontend/src/views/douyinColorAnalytics/VideoList.vue
frontend/src/views/douyinColorAnalytics/Annotate.vue
frontend/src/views/douyinColorAnalytics/Styles.vue
frontend/src/views/douyinColorAnalytics/Report.vue
frontend/src/views/douyinColorAnalytics/Health.vue
frontend/src/router/index.ts
```

采集器：

```text
tools/douyin-color-analytics-collector.user.js
tools/douyin-color-collector/collectorFieldWhitelist.js
tools/douyin-color-collector/globalScheduler.js
tools/douyin-color-collector/localQueue.js
tools/douyin-color-collector/uploadProtocol.js
docs/douyin-color-analytics-collector-install.md
```

测试：

```text
backend/tests/fixtures/douyin/
backend/tests/test_douyin_color_models.py
backend/tests/test_douyin_color_ingest.py
backend/tests/test_douyin_color_security.py
backend/tests/test_douyin_color_annotation.py
backend/tests/test_douyin_color_metrics.py
backend/tests/test_douyin_color_reports.py
backend/tests/test_douyin_color_exports.py
tests/douyin-color-collector/
frontend/tests/douyinColorAnalyticsAnnotate.spec.ts
frontend/tests/douyinColorAnalyticsReport.spec.ts
frontend/tests/douyinColorAnalyticsHealth.spec.ts
```

## 7. 完整上线开发任务

### Task 0: 生产预检、契约冻结和一条真实闭环

**Files:**
- Inspect: `/srv/huabang-ai-center/AGENTS.md`
- Inspect: `/srv/huabang-ai-center/backend/AGENTS.md`
- Inspect: `/srv/huabang-ai-center/backend/app/main.py`
- Inspect: `/srv/huabang-ai-center/backend/app/api/v1/router.py`
- Inspect: `/srv/huabang-ai-center/backend/app/models/__init__.py`
- Inspect: `/srv/huabang-ai-center/backend/alembic/env.py`
- Inspect: `/srv/huabang-ai-center/frontend/package.json`
- Inspect: `/srv/huabang-ai-center/frontend/src/router/index.ts`
- Inspect: `/srv/huabang-ai-center/deploy/`
- Create: `docs/plans/douyin-color-analytics-task0-evidence.md`
- Create: `backend/tests/fixtures/douyin/historical-20260728.sanitized.json`
- Create: `backend/tests/fixtures/douyin/historical-20260728.sanitized.sha256`

**Interfaces:**
- Produces: 实际源码 commit、工作分支、回滚点、PostgreSQL 版本、权限映射、任务队列结论、测试命令、正式 API origin、上传契约 v1、脱敏夹具和三视频语义证据。

- [ ] 只读记录当前生产 commit、PostgreSQL `SHOW server_version`、Alembic head、现有 Base 导入、鉴权依赖、角色、审计、后台任务、反向代理、备份和测试命令。
- [ ] 从生产对应 commit 创建隔离工作副本；不得直接在运行目录编辑。
- [ ] 用已登录 Chrome 复测目录和三条视频的 `analysis_type=1/7`，逐点保存页面/API 对照；所有证据先脱敏。
- [ ] 从已采集的 48 作品数据生成白名单夹具，必须保留 46 视频、2 图文跳过、64 位 ID、空曲线、429、业务错误和重复内容快照场景。
- [ ] 在预生产只配置一个真实抖音账号，记录 expected creator ID 的脱敏指纹；确认运营页面没有账号新增入口，启用第二账号被首期配置拒绝。
- [ ] 写契约测试，先验证 v2 关联冲突、跨账号同款、NULL 唯一和缺片 finalize 场景确实失败。
- [ ] 建立最小垂直闭环：浏览器采 1 条 → gzip 分片 → 服务端测试接收 → 数据库保存原始/归一曲线 → 后台只读页面显示；这是集成门禁，不是最终交付。
- [ ] 输出 Task 0 评审记录。未冻结账号隔离、快照关系、批次协议、部分索引、独立快照、原始/归一层、观察窗口、队列与权限前不得开始 Task 1。

**Verification:**

```powershell
ssh -o BatchMode=yes xiaohu@100.94.89.49 "cd /srv/huabang-ai-center && git rev-parse HEAD && psql --version"
```

Expected: 输出真实 commit 和 PostgreSQL 客户端版本；证据文档同时记录服务端版本。

### Task 1: 账号隔离、状态机、持久模型和迁移

**Files:**
- Create: `backend/app/models/douyin_color_analytics.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/douyin_color_analytics.py`
- Create: `backend/alembic/versions/20260729_01_douyin_color_analytics.py`
- Test: `backend/tests/test_douyin_color_models.py`

**Interfaces:**
- Produces: 第 2 节全部表、枚举、外键、检查约束和两个报告部分唯一索引。

- [ ] 写失败测试：相同账号重复款号/SKU、跨账号外键、首期启用第二账号、同账号/款色/日期/窗口/位置重复当前报告、相同快照被两个采集项引用、非法 focus 组合、非法状态和越界片段。
- [ ] 运行测试并保存迁移前失败证据。
- [ ] 实现模型和迁移；所有业务表显式带 `account_id`，禁止依赖间接 join 推断账号。
- [ ] 在空库执行 upgrade，在生产结构副本执行 upgrade，检查两个部分唯一索引和所有枚举。
- [ ] 运行 downgrade 只用于空测试库验证可逆语法；生产回滚不执行 downgrade。
- [ ] 提交并等待模型评审通过后进入 Task 2。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_models.py -v
alembic upgrade head
alembic current
```

Expected: 模型测试全通过，Alembic current 等于新 revision。

### Task 2: 安全接收、分片完成协议和采集健康

**Files:**
- Create: `backend/app/services/douyin_color_security_service.py`
- Create: `backend/app/services/douyin_color_ingest_service.py`
- Create: `backend/app/api/v1/douyin_color_analytics.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_douyin_color_security.py`
- Test: `backend/tests/test_douyin_color_ingest.py`

**Interfaces:**
- Consumes: Task 1 模型和状态枚举。
- Produces: `collector-config`、心跳、事件、parts、missing-parts、finalize、abandon、批次/采集项/快照查询 API。

- [ ] 写失败测试：非 gzip、解压炸弹、未知 schema、低脚本版本、敏感键、签名 URL、账号不匹配、非管理员配置账号、首期启用第二账号、part_count 修改、同编号不同 hash、乱序分片、缺片 finalize、24 小时过期和重复快照引用。
- [ ] 运行测试并确认每种错误返回冻结的错误码。
- [ ] 实现白名单解析、递归安全扫描、消息清洗、令牌账号解析、observed creator 校验和只对管理员开放的账号配置 API；首期不创建账号管理前端页面。
- [ ] 实现分片状态机、幂等、missing parts、服务器 batch hash、显式 finalize 和过期任务。
- [ ] 实现心跳状态推导、预期在线时段和版本漂移，禁止接收 query/hash。
- [ ] 用 48 条脱敏夹具验证 48 作品、46 视频、46 组留存/跳出成功、2 跳过；重复导入不增加快照但增加采集项引用。
- [ ] 提交并完成“浏览器 → API → DB → 原始曲线查看”阶段评审。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_security.py tests/test_douyin_color_ingest.py -v
```

Expected: 所有安全、协议和 48 条夹具测试通过。

### Task 3: 油猴采集器、全局限速、恢复和容量保护

**Files:**
- Create: `tools/douyin-color-analytics-collector.user.js`
- Create: `tools/douyin-color-collector/collectorFieldWhitelist.js`
- Create: `tools/douyin-color-collector/globalScheduler.js`
- Create: `tools/douyin-color-collector/localQueue.js`
- Create: `tools/douyin-color-collector/uploadProtocol.js`
- Create: `tests/douyin-color-collector/globalScheduler.test.cjs`
- Create: `tests/douyin-color-collector/localQueue.test.cjs`
- Create: `tests/douyin-color-collector/uploadProtocol.test.cjs`
- Create: `docs/douyin-color-analytics-collector-install.md`

**Interfaces:**
- Consumes: Task 2 collector-config 和上传 API。
- Produces: 可安装采集器、IndexedDB 可恢复队列、全局调度、T+2/T+7/T+30 任务、账号保护、容量告警和安全上传。

- [ ] 写失败测试：两个 worker 仍保持 1000ms 全局间隔、最多 2 个在途、429 退避、单项 5 次封顶、401/403 停止、账号切换停止、missing parts 恢复、80% 容量停止新采集、无签名字段落盘。
- [ ] 运行 Node 测试并保存失败证据。
- [ ] 实现目录分页、观察窗口任务、失败补采、内存态真实 URL 学习和字段白名单。
- [ ] 实现全局调度器、两个在途请求、重试/抖动和坏数据隔离。
- [ ] 实现 IndexedDB 固定分片、恢复、导出未上传批次、人工放弃和 7 天已完成清理。
- [ ] 实现心跳、可见性、唤醒漂移、账号观察、版本配置和控制面板。
- [ ] 油猴仅配置正式 API origin 的唯一 `@connect`，通过 `GM_xmlhttpRequest` gzip 上传。
- [ ] 用真实 Chrome 执行：可见页、后台页、系统休眠恢复、网络断开、服务器拒绝、账号切换和 Chrome 重启场景。
- [ ] 提交并完成采集可靠性评审。

**Verification:**

```bash
node --test tests/douyin-color-collector/*.test.cjs
```

Expected: 限速、恢复、容量、安全和账号保护测试全部通过。

### Task 4: 商品、主要衣物双窗口标注和审核

**Files:**
- Create: `backend/app/services/douyin_color_annotation_service.py`
- Modify: `backend/app/api/v1/douyin_color_analytics.py`
- Create: `backend/tests/test_douyin_color_annotation.py`
- Create: `frontend/src/api/douyinColorAnalytics.ts`
- Create: `frontend/src/views/douyinColorAnalytics/VideoList.vue`
- Create: `frontend/src/views/douyinColorAnalytics/Annotate.vue`
- Create: `frontend/src/views/douyinColorAnalytics/Styles.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `frontend/tests/douyinColorAnalyticsAnnotate.spec.ts`

**Interfaces:**
- Produces: 款/色/SKU CRUD、主要分析衣物 focus 状态、标注状态机、版本锁、重叠审批和审计。

- [ ] 写失败测试：跨账号商品访问、SKU 冲突、clear_primary 缺款色、multi_focus/unclear 携带款色、超视频时长、未审批重叠、非 clear_primary 参与计算、同一片段分配多件衣物、版本冲突和越权审批。
- [ ] 运行后端和前端失败测试。
- [ ] 实现账号限定 CRUD 和 SKU Excel 导入错误行；运营页面不提供账号新增入口。
- [ ] 实现原作品安全 pathname 打开、曲线时间轴、整秒吸附、clear_primary/multi_focus/unclear、focus 备注、draft→submitted→approved/rejected、删除/恢复和审计。
- [ ] 用真实多件穿搭视频完成：单一主要衣物、从上衣切换到裤子的拆段、多重点排除、无法判断排除、同款同色再次出现、跨色重叠审批、删除和恢复。
- [ ] 由 1 名运营试标至少 10 条历史视频并记录单条耗时和歧义；据此评估 46 条历史数据的正式整理排期。
- [ ] 提交并完成标注闭环评审。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_annotation.py -v
cd ../frontend
npm test -- douyinColorAnalyticsAnnotate.spec.ts
```

Expected: 后端状态/权限与前端交互测试通过。

### Task 5: 归一化、独立指标、位置和观察窗口

**Files:**
- Create: `backend/app/services/douyin_color_curve_service.py`
- Create: `backend/app/services/douyin_color_metrics_service.py`
- Create: `backend/tests/test_douyin_color_metrics.py`

**Interfaces:**
- Consumes: 已批准片段、原始快照、目录快照和观察窗口。
- Produces: 独立 retention/bounce 状态、主要衣物资格过滤、位置字段、质量状态和 video-color 指标。

- [ ] 写失败测试：0..1、0..100、unknown 单位、重复时间点、超界值、等/不等间隔、边界插值、超 1 秒、同一主要衣物多个片段、multi_focus/unclear 排除、同一片段不得重复归给多件衣物、留存成功而跳出失败、T+2/T+7/T+30 隔离和位置段。
- [ ] 运行测试并保存失败证据。
- [ ] 实现白名单 raw → normalization_version 的纯函数；禁止修改 raw_response_json。
- [ ] 实现 focus 资格过滤、插值、梯形积分、片段时长聚合、相对位置和 dominant segment。
- [ ] 独立选择 retention/bounce 快照和计算状态；跳出语义门控不得影响留存。
- [ ] 用三条手算样本和历史脱敏夹具核对指标。
- [ ] 提交并完成统计内核评审。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_metrics.py -v
```

Expected: 所有单位、曲线、位置、窗口和独立状态测试通过。

### Task 6: 异步重算、报告快照和安全导出

**Files:**
- Create: `backend/app/services/douyin_color_report_service.py`
- Create: `backend/app/services/douyin_color_export_service.py`
- Create: `backend/app/workers/douyin_color_calculation_worker.py`
- Modify: `backend/app/api/v1/douyin_color_analytics.py`
- Create: `backend/tests/test_douyin_color_reports.py`
- Create: `backend/tests/test_douyin_color_exports.py`
- Create: `frontend/src/views/douyinColorAnalytics/Report.vue`
- Test: `frontend/tests/douyinColorAnalyticsReport.spec.ts`

**Interfaces:**
- Produces: dirty→job→指标→报告闭环、可复现报告、有效/排除质量计数、样本门槛、位置解释、语义门控和安全导出。

- [ ] 写失败测试：重复 job、worker 崩溃租约恢复、历史重采、标注/focus 变更、eligible 视频去重、multi_focus/unclear 排除计数、留存 3 条门槛、稳定性 5 条门槛、样本标准差、当前/历史报告唯一、T 窗口与位置筛选隔离、公式注入和越权导出。
- [ ] 运行测试并保存失败证据。
- [ ] 复用现有生产任务队列；若 Task 0 确认不存在，则实现本计划冻结的 PostgreSQL worker。
- [ ] 实现事件驱动 dirty、幂等 calculation_jobs、重试、stale 报告和新快照生成。
- [ ] 实现账号/款号/观察窗口/全部或前中后位置筛选、等权基线、视频加权和曝光参考。
- [ ] 实现平均留存榜、稳定性榜和条件化跳出榜；显示位置、片段长度、有效视频样本数、排除多重点片段数、排除无法判断片段数和固定说明。
- [ ] 实现 CSV/XLSX 公式转义、元数据和导出审计。
- [ ] 后来重采/修改标注后验证旧报告 hash 不变，新报告有新 hash。
- [ ] 提交并完成统计报告评审。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_reports.py tests/test_douyin_color_exports.py -v
cd ../frontend
npm test -- douyinColorAnalyticsReport.spec.ts
```

Expected: 重算、报告、门槛、可复现和导出安全测试通过。

### Task 7: 健康页、权限、备份恢复和生产发布

**Files:**
- Create: `frontend/src/views/douyinColorAnalytics/Health.vue`
- Test: `frontend/tests/douyinColorAnalyticsHealth.spec.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `backend/app/api/v1/douyin_color_analytics.py`
- Create: `docs/runbooks/douyin-color-analytics-operations.md`
- Create: `docs/runbooks/douyin-color-analytics-backup-restore.md`
- Create: `docs/runbooks/douyin-color-analytics-rollback.md`

**Interfaces:**
- Produces: 生产健康、告警、权限、维护手册、备份恢复证据和四阶段发布记录。

- [ ] 写失败测试：夜间 expected offline 不告警、工作时段 unexpected offline 告警、hidden/suspended 不误报故障、版本漂移、队列 80%、不完整批次、权限和功能开关。
- [ ] 实现健康页：账号、脚本、页面状态、最后心跳、最后完整批次、队列、缺片、失败分类、重算任务、预期时段和版本漂移。
- [ ] 完成六类权限映射与所有审计动作的回归。
- [ ] 在预生产执行备份、恢复、令牌轮换、429、缺片、worker 崩溃、浏览器休眠、账号切换和应用回滚演练。
- [ ] 按 A→B→C→D 开关逐阶段发布；每阶段保存版本、批次、报告、健康、审计和回滚点。
- [ ] 生产执行一个真实日期范围和 T+7 重采，确认数据库、日志、队列和导出无平台敏感值。
- [ ] 生产观察至少 3 个预期在线日后，再决定是否进入 D 阶段；异常保持灰度，不伪报上线完成。

**Verification:**

```bash
cd backend
pytest tests/test_douyin_color_*.py -v
cd ../frontend
npm test
npm run build
```

Expected: 全部模块测试通过、前端构建成功；另附预生产和生产真实验收证据。

## 8. 开发周期与业务周期

工程周期估计：

| 人员配置 | 工程周期 | 加 20%～30% 集成缓冲后 |
| --- | ---: | ---: |
| 1 名熟悉现有系统的全栈 | 8～12 周 | 10～16 周 |
| 1 后端 + 1 前端/采集器 | 5～8 周 | 6～11 周 |
| 后端、前端、采集器各 1 人 + 运维 | 4～6 周 | 5～8 周 |

关键路径：

1. 第 1 周：Task 0 和一条真实垂直闭环；
2. 第 2～3 周：Task 1～3 的模型、协议、采集可靠性；
3. 第 3～4 周：Task 4 标注闭环和历史试标；
4. 第 4～5 周：Task 5～6 指标、观察窗口和重算；
5. 第 5～6 周：Task 7 生产加固和分阶段发布。

这些是集成门禁，不是拆成没有后续的 MVP。任何并行开发都必须遵守模型→协议→采集/标注→统计→发布的依赖关系。

历史 46 条视频预计需要半天到一天纯标注，加复核；代码上线日不等于报告有数据日。平均榜需每色至少 3 条不同视频，稳定性榜需至少 5 条，因此可信业务结论通常还需要 2～6 周样本积累。

## 9. 上线阻塞清单

- [ ] 快照去重关系允许多个 collection item 引用同一 snapshot；
- [ ] 所有商品、标注、指标、报告、查询和部分索引均含 account_id；
- [ ] observed creator 与上传令牌账号不匹配时停止采集；
- [ ] receiving→finalize→completed 状态机、missing parts、乱序和 24 小时过期通过；
- [ ] PostgreSQL 当前报告和历史 revision 唯一索引通过并发测试；
- [ ] raw_response_json 与 normalized_curve_json 分离且可回放；
- [ ] 留存和跳出独立快照、独立状态、独立样本数；
- [ ] clear_primary 是唯一入榜 focus 状态，一段曲线最多归给一件主要衣物；
- [ ] 报告显示 eligible 视频数、multi_focus 排除数和 unclear 排除数；
- [ ] T+2/T+7/T+30、出现位置、片段长度和播放量口径进入模型与报告；
- [ ] 平均榜 3 条、稳定性榜 5 条且标准差使用 n-1；
- [ ] 计划、数据库、API、页面、权限、测试和审计中不存在分组实验功能；
- [ ] 采集事件和当前页面字段不含 URL query、hash 或任意响应正文；
- [ ] 两个 worker 共用 1000ms 全局发起限速，失败次数有上限；
- [ ] 预期在线时段、hidden、suspended、auth_required 和 queue blocked 不产生错误告警；
- [ ] IndexedDB 达 80% 停止新采集，未上传数据不静默删除且可导出恢复；
- [ ] dirty→calculation_jobs→worker→报告快照全链路可恢复；
- [ ] schema/script 版本兼容和 collector-config 可用；
- [ ] 数据保留、每日备份、RPO 24h、RTO 8h、季度恢复演练有证据；
- [ ] 六类权限和所有高风险动作审计通过；
- [ ] 原始 JSON 白名单、服务器递归扫描和导出公式转义通过；
- [ ] 三条真实视频决定跳出功能开关，未验证时不出现跳出榜；
- [ ] A/B/C/D 四阶段均有评审、版本、批次、报告、健康和回滚证据；
- [ ] 生产连续 3 个预期在线日无阻塞故障后才对全部授权运营开放。

## 10. v3.1 最终冻结结论

最终分析链路固定为：

```text
首期唯一启用的自有抖音账号
-> 自有视频
-> 人工选择视频片段
-> 每个片段确定一件主要分析衣物
-> 同款不同颜色
-> 留存和平台跳出曲线
```

主要输出固定为平均留存、留存下降、留存波动、语义验证后的平台跳出曲线指标、前中后出现位置、有效视频样本数、排除片段质量计数和相对其他颜色差值。

第一版不分析模特、脚本、场景、投流条件、发布时间段、搭配效果、多件衣物联合归因或因果实验。观察窗口继续保留，只用于防止 T+2、T+7、T+30 数据混合；位置字段继续保留，只用于解释和筛选。

底层多账号隔离保留，首期只配置并启用一个真实账号；运营后台不提供新增账号入口。主要衣物 focus 规则、无分组报告、留存/跳出独立计算、分片和快照关系、跨语言 hash、健康状态机、异步任务、报告锁和观察窗口快照选择均由本计划冻结，不再扩展业务范围。

需求在 v3.1 停止扩展。下一步直接进入 Task 0 的真实闭环验证；Task 1～7 仍需逐阶段评审，只有完整生产阻塞清单通过，才能称为模块上线完成。
