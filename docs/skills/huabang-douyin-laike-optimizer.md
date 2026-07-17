# 华邦抖音来客投流优化 Skill 项目契约

## 决策顺序

1. 读取 `POST /life-data/status` 上报的采集器健康状态。
2. 使用 `GET /life-data-analysis/overview` 核对同周期消耗、实际核销、退款和 `attribution_quality`。
3. 使用 `GET /investment-decisions/overview` 读取最新已保存建议，区分 `DeepSeek 增强建议` 与 `规则兜底`。
4. 使用 `GET /investment-decisions/history` 和详情接口复盘人工决定、实际预算及 24/72/168 小时结果。
5. 使用 `GET /investment-decisions/patterns/daily` 读取 7/30/90 天同期观察。
6. 数据不足时只补采；所有建议保持 `requires_human_confirm: true` 和 `executed: false`。

## 地域口径

- 地域模块统一解释为“投放触达人群居住地”的广告消耗分布，不是门店或核销地域。
- `region_province` 表示投放触达人群居住省份消耗。
- `region_city` 表示投放触达人群居住城市消耗。
- 省份与城市不得混排。
- 只有地域消耗、没有地域成交和实际核销时，不得建议某地域加投。

## DeepSeek 与规则边界

- DeepSeek 只接收标准化事实、历史结果和证据引用，不读取原始会话数据。
- DeepSeek 负责解释历史环境和生成结构化建议；规则负责数据门槛、归因等级、动作集合、预算上限和止损。
- 模型超时、非 JSON、引用不存在证据、超预算、越权动作或升级归因等级时使用规则兜底。
- 每日规律只描述同期观察；没有直接归因或对照实验时不得声称因果。
- Skill 不直接执行投放，不修改账号、预算、计划或素材。
