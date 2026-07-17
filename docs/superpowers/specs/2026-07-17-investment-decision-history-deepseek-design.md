# 华邦投流决策历史数据库与 DeepSeek 增强设计

## 1. 目标

在华邦 AI 中台现有“投流优化”页面和 LifeData 生意经采集链路上，建立可追溯、可复盘、可持续积累规律的投流决策闭环。

采用已确认的组合方案：

- **方案 2 为主：** 每个完整投流数据周期形成标准化指标快照；仅当输入发生变化时，使用 DeepSeek 生成一次结构化建议并保存。页面读取已保存结果，不因刷新重复调用模型。
- **方案 3 为辅：** 每日离线汇总最近 7 天、30 天和可用历史，使用 DeepSeek 生成一次环境规律总结，供后续建议引用。
- **规则引擎兜底：** 数据门槛、归因质量、预算上限、止损条件和人工确认要求由确定性规则控制。DeepSeek 不可用、超时或输出不合规时，保存失败原因并返回规则建议。

系统只生成建议和保存人工执行记录，不登录投放平台，不直接创建、暂停或修改投放计划。

## 2. 当前基线与问题

线上已经具备：

- `app.life_data_capture`：保存脱敏后的生意经请求与响应，原始数据保留 90 天；
- `app.life_data_video_snapshot`：保存视频指标快照；
- `app.life_data_alert_event`：保存自然流量规则预警；
- `app.life_data_collector_state`：保存采集器健康、队列和模板状态；
- `GET /life-data-analysis/overview`：从最近 300 条采集记录计算最新一期概览；
- DeepSeek JSON 调用、超时处理和 AI 调用日志能力；
- 投流页面的消耗、广告成交、实际核销、退款、素材、人群、地域和趋势展示。

当前不足：

1. 页面中的“AI 下一步建议”实际由固定 ROI 阈值生成，没有调用 DeepSeek。
2. 建议没有独立入库；页面刷新后只能重新计算，无法追溯当时看到的证据和规则版本。
3. 没有保存“采纳或拒绝—实际预算—24/72/168 小时结果”，无法评价建议是否有效。
4. 原始 JSON 适合追溯但不适合长期分析；90 天清理后无法继续比较历史环境。
5. 省级 `ProvinceDistribution` 与城市级 `CityDistribution` 被合并为同一个地域列表，导致“贵州省”和“贵阳市”混排。
6. “贵阳及周边消耗分布”实际是投放触达人群居住地消耗分布，不是门店、成交或实际核销地域分布。
7. 当前归因可能是 `period_estimate`，不能把账户同期核销描述为素材级精确归因。

## 3. 设计原则

- 唯一业务数据源仍是抖音来客生意经真实接口数据。
- 实际核销金额是第一结果口径；广告支付金额仅作为平台内过程指标。
- 平台直接关联、同期估算和数据缺失分别标记为 `exact`、`period_estimate`、`missing`。
- 金额在数据库和 AI 输入中统一使用整数分，展示层才转换为元。
- DeepSeek 只接收标准化数据、证据引用和历史结果，不接收完整原始响应。
- 不向模型发送 Cookie、Authorization、会话 Token、动态签名、签名密钥或个人敏感信息。
- 每条建议必须是 `requires_human_confirm=true`、`executed=false`；只有人工登记后才能产生执行记录。
- 同一个输入哈希只生成一次建议，避免重复调用、重复记录和页面刷新导致建议漂移。
- 历史指标、决策、执行和结果长期保留；90 天清理策略只适用于原始采集表。

## 4. 总体架构

```text
生意经只读接口
  -> LifeData 脱敏采集
  -> 原始采集表（90 天）
  -> 标准化指标快照（长期）
  -> 数据完整性与归因规则
  -> DeepSeek 结构化建议
  -> 决策与建议历史
  -> 人工采纳/拒绝
  -> 实际执行登记
  -> 24/72/168 小时结果快照
  -> 每日环境规律总结
  -> 下一周期建议引用历史规律
```

页面不直接触发 DeepSeek。定时任务或完整采集周期完成事件负责生成；页面只读取最近一次成功建议、规则兜底建议和历史记录。

## 5. 数据库设计

所有新表使用 PostgreSQL `app` schema，时间使用带时区时间戳，金额使用 `BigInteger` 分。

### 5.1 `investment_metric_snapshot`

保存长期标准化指标，是历史分析和 DeepSeek 输入的事实表。

主要字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 主键 |
| `account_id` | 生意经账号 |
| `stat_start`, `stat_end` | 统计周期 |
| `dimension_type` | `account/material/campaign/plan/audience_age_gender/region_province/region_city/hour/store` |
| `dimension_key` | 维度稳定标识 |
| `dimension_label` | 展示名称 |
| `spend_fen` | 投放消耗 |
| `ad_orders` | 广告订单数 |
| `ad_pay_gmv_fen` | 广告支付金额 |
| `pay_gmv_fen` | 经营支付金额 |
| `verified_gmv_fen` | 实际核销金额 |
| `verified_count` | 核销券数 |
| `refund_gmv_fen` | 退款金额 |
| `plays`, `interactions`, `completion_rate` | 流量指标 |
| `attribution_quality` | `exact/period_estimate/missing` |
| `source_capture_ids` | 证据原始采集 ID 数组 |
| `metrics_extra` | 已验证但尚未升为固定列的扩展指标 |
| `input_hash` | 标准化内容哈希 |
| `captured_at`, `created_at` | 数据与入库时间 |

唯一约束：

`account_id + stat_start + stat_end + dimension_type + dimension_key + input_hash`

省份和城市必须分别保存为 `region_province`、`region_city`，禁止再次合并为一个 `region` 排行。

### 5.2 `investment_decision_run`

记录一次建议生成过程，确保模型调用、规则兜底和输入版本可审计。

主要字段：

- `id`, `account_id`, `stat_start`, `stat_end`；
- `trigger_type`：`period_complete/daily_summary/manual_rebuild`；
- `input_hash`：本次标准化输入哈希，主建议场景唯一；
- `attribution_quality`, `data_completeness`；
- `rule_version`, `prompt_version`；
- `provider`, `model_used`；
- `status`：`generated/fallback/blocked/failed`；
- `fallback_reason`, `latency_ms`, `token_usage`；
- `source_snapshot_ids`, `created_at`, `completed_at`。

### 5.3 `investment_recommendation`

保存一次生成结果中的一条建议。

主要字段：

- `decision_run_id`；
- `action`：`collect_more_data/stop/reduce/maintain/small_increase/increase`；
- `target_type`, `target_key`, `target_label`；
- `title`, `reasoning`；
- `budget_min_fen`, `budget_max_fen`；
- `review_window_hours`, `stop_loss`；
- `confidence`：`low/medium/high`；
- `evidence_refs`：引用快照和指标，不复制原始敏感数据；
- `requires_human_confirm=true`, `executed=false`；
- `created_at`。

只有 `exact` 且历史样本门槛满足时允许 `high`；`period_estimate` 最高只能是 `medium`；`missing` 只能生成 `collect_more_data` 和 `low`。

### 5.4 `investment_execution_record`

保存人工决定和实际执行事实，不调用抖音接口。

主要字段：

- `recommendation_id`；
- `decision`：`accepted/rejected/partially_accepted/expired`；
- `confirmed_by`, `confirmed_at`；
- `actual_budget_fen`；
- `external_campaign_id`, `external_plan_id`, `external_creative_id`；
- `executed_at`, `execution_note`；
- `created_at`, `updated_at`。

`executed` 只表示用户已登记实际执行，不能根据点击“我知道了”自动置为真。

### 5.5 `investment_outcome_snapshot`

在执行后保存分阶段结果。

主要字段：

- `execution_record_id`；
- `window_hours`：固定为 `24/72/168`；
- `observed_at`；
- `incremental_spend_fen`、`incremental_ad_pay_gmv_fen`；
- `incremental_verified_gmv_fen`、`incremental_verified_count`；
- `incremental_refund_gmv_fen`；
- `ad_pay_roi`, `verified_roi`, `refund_adjusted_verified_roi`；
- `attribution_quality`, `source_snapshot_ids`；
- `created_at`。

没有平台直接关联键时，结果必须标记 `period_estimate`，不得暗示建议造成了对应核销。

### 5.6 `investment_environment_summary_daily`

保存每日环境规律，不在页面打开时实时生成。

主要字段：

- `account_id`, `summary_date`；
- `lookback_days`：`7/30/90`；
- `input_hash`, `provider`, `model_used`, `prompt_version`；
- `patterns`：已验证的时段、地域、素材生命周期和核销滞后观察；
- `risks`：数据缺失、异常波动、外溢和归因限制；
- `sample_size`, `confidence`；
- `evidence_refs`, `created_at`。

唯一约束：`account_id + summary_date + lookback_days + input_hash`。

## 6. 标准化与地域修正

标准化器从原始采集表读取数据，但必须将来源路径、响应模块和统计层级保留下来。

地域规则：

- `ProvinceDistribution` 只生成 `region_province`；
- `CityDistribution` 只生成 `region_city`；
- `city_resident`、`province_resident` 表示投放触达人群居住地；
- 当前 `sub_ad_cost`、`sub_ad_cost_rate` 只能解释为地域消耗和消耗占比；
- 没有地域成交或核销时，不生成地域加投结论；
- 页面将“贵阳及周边消耗分布”改为“投放人群地域消耗分布（按居住地）”；
- 页面省份、城市分开展示，并明确“仅代表广告消耗流向，不能单独判断地域效果”。

年龄和性别同样先作为消耗结构展示；未获得对应成交和核销前，不生成某年龄或性别应加投的结论。

## 7. 主方案：周期建议生成

### 7.1 触发条件

完整采集周期完成后检查：

1. 广告分组与经营分组统计周期一致；
2. 至少存在 `spend_fen`、`verified_gmv_fen`、`stat_date`；
3. 标准化快照成功写入；
4. 本次 `input_hash` 尚未生成决策；
5. 距离上一次模型生成至少 60 分钟。

数据不足时不调用 DeepSeek，直接保存 `blocked` 决策运行和 `collect_more_data` 规则建议。采集分组恢复并形成新输入哈希后可重新生成。

### 7.2 确定性规则前置

规则引擎先计算：

- 数据完整性和统计周期一致性；
- 广告支付 ROI、实际核销 ROI、退款后核销 ROI、核销 CPA；
- 预算硬上限、建议动作允许集合；
- `exact/period_estimate/missing`；
- DeepSeek 可引用的证据列表；
- 不允许加投的阻断原因。

若实际核销 ROI 不可计算、周期不一致或归因是 `missing`，DeepSeek 不能输出加投建议。

### 7.3 DeepSeek 输入

模型输入只包含：

- 当前账户及各维度标准化快照；
- 最近 7/30/90 天可比指标；
- 已执行建议的 24/72/168 小时结果；
- 最近每日环境规律摘要；
- 归因质量、样本量和缺失字段；
- 规则允许动作、预算上限和证据引用 ID。

不发送完整 `request_payload`、`response_payload`、会话字段和无关业务数据。

### 7.4 DeepSeek 输出契约

使用 JSON 模式，输出结构固定为：

```json
{
  "decision_summary": "本周期判断",
  "recommendations": [
    {
      "action": "reduce",
      "target_type": "account",
      "target_key": "account_id",
      "title": "降低无效消耗",
      "reasoning": "基于实际核销而非广告支付",
      "budget_min_fen": 3000,
      "budget_max_fen": 8000,
      "review_window_hours": 24,
      "stop_loss": "新增消耗10000分仍无新增核销时停止",
      "confidence": "medium",
      "evidence_refs": ["snapshot:123"]
    }
  ],
  "pattern_observations": [],
  "data_limitations": ["素材到核销仅为同期归因估算"]
}
```

后端必须再次校验动作、金额、证据引用、置信度和止损条件。模型不能引用输入中不存在的数据，不能把 `period_estimate` 改成 `exact`，不能输出自动执行状态。

### 7.5 模型失败与规则兜底

以下情况进入 `fallback`：

- DeepSeek 超时或网络失败；
- 返回非 JSON；
- JSON Schema 校验失败；
- 引用不存在的证据；
- 建议动作超出规则允许集合；
- 建议预算超过规则硬上限；
- 将估算归因表述为精确归因。

兜底建议使用当前确定性规则生成，同时保存模型失败摘要、模型名、提示词版本和输入哈希，页面明确显示“规则兜底建议”。

## 8. 辅助方案：每日环境规律总结

北京时间每日 06:30 对前一日及可用历史运行一次离线总结。分别生成 7 天、30 天和最多 90 天窗口；历史不足时缩短窗口并降低置信度。

允许总结的规律：

- 星期和时段的消耗、广告成交、实际核销变化；
- 素材从起量到衰退的生命周期；
- 实际核销相对广告支付的滞后；
- 省内外消耗外溢；
- 已执行建议在 24/72/168 小时后的结果；
- 相同动作在不同历史环境中的成功或失败情况。

不允许把相关性描述为因果。没有对照组或直接归因时，必须使用“同期观察”“可能相关”等表述。历史记录不足时输出“样本不足”，不得编造规律。

## 9. 服务与 API

保留现有采集接口并新增只读/登记型接口：

- `GET /investment-decisions/overview`：最新指标、最新建议、生成来源、归因质量和最近环境摘要；
- `GET /investment-decisions/history`：按日期、动作、目标、采纳状态分页查询；
- `GET /investment-decisions/{id}`：查看输入周期、证据、规则/模型版本和后续结果；
- `POST /investment-decisions/{id}/decision`：登记采纳、拒绝或部分采纳；
- `POST /investment-decisions/{id}/execution`：登记实际预算和外部计划标识，不调用平台；
- `GET /investment-patterns/daily`：查询 7/30/90 天环境规律。

生成接口不暴露给普通页面。周期生成和每日总结由后台任务触发；如未来需要人工重建，仅管理员可操作并仍受输入哈希幂等约束。

## 10. 页面设计

`/app/marketing/investment` 调整为四个明确区域：

1. **本周期经营结果：** 消耗、广告成交、实际核销、退款及归因质量。
2. **最新建议：** 标明“DeepSeek 增强建议”或“规则兜底建议”，展示生成时间、证据、预算、止损、置信度和人工确认状态。
3. **决策历史：** 展示建议、采纳状态、实际预算以及 24/72/168 小时结果。
4. **环境规律：** 展示每日总结和证据窗口，不把相关性写成因果。

地域模块改为“投放人群地域消耗分布（按居住地）”，提供“省份/城市”切换。没有地域成交和核销时只显示消耗、占比和外溢提示，不显示地域加投建议。

当前“人工确认后执行”按钮改成真实登记流程：

- 采纳、拒绝、部分采纳；
- 采纳后填写实际预算和可选计划/素材标识；
- 点击提示框不代表已执行；
- 执行后显示等待 24/72/168 小时结果。

## 11. Skill 完善

更新 `huabang-douyin-laike-optimizer` Skill：

1. 先读取采集器状态和最新完整周期；
2. 再读取最新建议、历史执行结果和环境规律；
3. 明确区分 DeepSeek 增强建议与规则兜底建议；
4. 地域数据必须区分省级与城市级，并注明是用户居住地消耗；
5. 没有地域成交或核销时禁止建议某地域加投；
6. 只有同期估算时必须标注 `period_estimate`；
7. 数据不足时只建议补采，不调用模型补数；
8. 所有建议继续要求人工确认，Skill 不执行投放；
9. 复盘时以实际执行记录和 24/72/168 小时结果为准；
10. 不把历史相关性描述为投放造成的因果效果。

Skill 的数据契约同步增加新表、接口、DeepSeek JSON 契约、历史复盘字段和地域层级语义。

## 12. 历史回填

上线后对当前仍保留的 90 天原始采集执行一次幂等回填：

- 生成标准化指标快照；
- 正确拆分省份与城市；
- 保留源采集 ID 和归因质量；
- 生成可用于规律分析的历史指标。

历史期间没有真实人工决策和执行记录，因此禁止伪造历史建议、采纳或执行结果。DeepSeek 可以对回填指标生成“历史观察摘要”，但必须标记为回顾性分析，不得伪装成当时生成的建议。

## 13. 安全、成本与可观测性

- 复用现有 DeepSeek 配置和调用客户端，增加独立的投流模型、超时和提示词版本配置；
- 记录实际 `provider`、`model_used`、耗时、Token 用量和失败摘要，不记录 API Key；
- 主建议最多每 60 分钟一次，且相同输入哈希不重复调用；
- 每日环境总结每个窗口每天最多一次；
- AI 输入大小受限，历史明细先在后端聚合，禁止把全部原始 JSON 发送给模型；
- 数据库写入和模型调用解耦，模型失败不能阻塞采集与指标快照；
- 所有写入任务幂等，可安全重试；
- 生成、兜底、阻断和失败分别计数并监控。

## 14. 测试与验收

### 14.1 数据库与标准化

- 迁移可升级、可回滚；
- 相同输入重复处理不会产生重复快照或决策；
- 省份与城市不会混排或重复汇总；
- 金额全部按分存储；
- 原始数据清理后历史指标、建议和结果仍存在；
- 回填不会制造历史执行记录。

### 14.2 DeepSeek 与规则

- 完整数据只调用一次 DeepSeek；
- 页面刷新不调用模型；
- 数据缺失、周期不一致或 `missing` 时不生成加投；
- `period_estimate` 不能被模型升级为 `exact`；
- 非 JSON、超时、越权动作、超预算和伪造证据均进入规则兜底；
- 所有建议均为 `requires_human_confirm=true`、`executed=false`。

### 14.3 执行与结果

- 单击确认提示不会创建执行记录；
- 采纳、拒绝、部分采纳状态可追溯；
- 24/72/168 小时结果分别保存且幂等；
- 没有直接关联时结果显示同期估算；
- 建议详情能够追溯到指标快照和原始采集 ID。

### 14.4 页面与 Skill

- 最新建议明确显示 DeepSeek 或规则来源；
- 历史页面显示建议、人工决定、实际预算和后续结果；
- 地域模块区分省份与城市并解释居住地口径；
- 没有地域核销时不显示地域加投结论；
- Skill 对缺失数据、估算归因、模型失败和人工确认的处理符合本设计。

### 14.5 生产验收

1. 执行迁移并核对新表与约束；
2. 回填现有原始数据，核对快照数量、统计周期和地域拆分；
3. 完成一个真实完整采集周期，确认只生成一个决策运行；
4. 验证 DeepSeek 成功建议和模拟失败时规则兜底；
5. 人工登记一条测试决策，确认没有调用投放平台；
6. 验证页面历史、证据和环境规律可追溯；
7. 观察至少一个 24 小时结果窗口后再确认闭环有效。

## 15. 实施边界与顺序

第一阶段按以下顺序实施：

1. 新表、标准化器和历史回填；
2. 决策规则、DeepSeek JSON 生成与持久化；
3. 人工决定、执行登记和结果快照；
4. 页面历史、地域修正和规律展示；
5. 每日环境总结；
6. Skill 与数据契约更新；
7. 完整测试、迁移演练和生产验收。

本阶段不包含自动投放、自动修改预算、跨平台归因、读取投放账号秘密、用模型补齐缺失数据或声称未经实验验证的因果提升。
