# 华邦老板经营指挥台三阶段总计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有华邦经营中台升级为老板每天可用的经营指挥台，让老板在 30 秒内看清昨日经营结果、当前风险和今日责任人，并形成“看得懂、查得出、推得动”的经营闭环。

**Architecture:** 继续使用现有 PostgreSQL 数据分层、`dm.dm_boss_daily_report`、经营日报、规则引擎、库存预警和任务状态机，不新建重复系统。所有外部数据先同步到本地 ODS/DWD/DWS，再由统一经营快照聚合；前端只消费带来源、状态和更新时间的后端指标，不自行拼业务口径。三阶段按“数据可信与下钻 -> 稽核、利润与任务闭环 -> AI 自动建议与移动端”顺序推进，每阶段均可独立验收。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy Async、PostgreSQL、Alembic、Redis/数据库锁、Vue 3、TypeScript、Element Plus、Vite、pytest、Node.js test、Playwright、百胜 E3ERP API、钉钉 API。

## Global Constraints

- 销售只统计 7 家门店：`134681`、`285204`、`285702`、`185805`、`185808`、`285101`、`285102`。
- 库存与 VIP 范围只统计上述 7 家门店及 `GZ001`、`GZ002`、`GYNG`；编码统一转大写，兼容 `gz002`。
- 销售额口径固定为：VIP卡消费 + 收钱吧POS机 + 收钱吧扫码 + 收钱吧胜券扫 + 五月前储值 + 现金 + 线上支付。
- 实收金额口径固定为：收钱吧POS机 + 收钱吧扫码 + 收钱吧胜券扫 + 现金 + 线上支付 + 充值金额 - 退款金额。
- 百胜结算代码 `011` 为线上销售；`000`、`003`、`004`、`666`、`971` 为线下销售；总销售额必须等于线上销售加线下销售。
- 库存只读“外穿衣物库存”统一视图；百胜原始库存完整保留。鞋、袜、围巾、皮带、包、赠品、内衣等不进入经营库存。
- 无成本 SKU 不计库存金额；库存数量仍保留。毛利必须返回成本覆盖率，覆盖不完整时状态为 `estimated`。
- 库龄按 FIFO 入库批次计算；无法匹配入库历史的数量和金额单列“库龄未知”，不得并入 90/180 天库龄。
- VIP 当前余额以百胜会员主档 `CZ_DQJE` 为准，不从交易流水反推；正余额计入资产，负余额单列异常，不相互抵消。
- 每个指标必须返回 `ready`、`estimated`、`pending_data` 或 `stale`，并附 `source`、`as_of`、`reason`。
- 线上销售、客流、试穿率、完整费用、导购归属等没有可靠来源时显示“待接入”，不得按零参与计算或 AI 结论。
- 费用未完整接入前不得输出净利润、经营利润或“公司是否盈利”的确定性结论。
- AI 只归纳确定性指标与规则结果；AI 不可用时必须回退模板摘要，不影响日报、预警和任务生成。
- `critical/risk` 异常只自动创建任务草稿，不自动派发；必须由老板或主管确认。
- 所有同步、快照、预警和任务草稿生成必须幂等，失败保留上次成功数据，不删除可信快照。
- 业务日期和调度统一按 Asia/Shanghai；每日经营快照北京时间 `06:30` 生成，即服务器 UTC `22:30`。
- 内容区遵守项目 UI 记忆：浅色背景、白色卡片、紧凑高密度布局；只有左侧导航保持深色。
- 保留现有 API 字段和路由，新增字段采用非破坏性扩展，避免网页及移动端旧调用失效。
- 禁止在生产目录覆盖与本计划无关的未提交改动；部署前必须记录变更文件、数据库版本和回滚点。

---

## 当前基线（2026-07-14）

| 能力 | 当前入口 | 基线判断 | 本计划处理 |
| --- | --- | --- | --- |
| 统一经营快照 | `backend/app/services/command_center_service.py`、`dm.dm_boss_daily_report` | 已有基础实现 | 第一阶段补齐状态、来源、重算与验收 |
| 老板首页 | `/app/dashboard` | 已有核心卡片、销售模块、风险和行动 | 第一阶段统一指标和下钻 |
| 经营日报 | `/app/report` | 已有日报和近 14 日记录 | 第一阶段补足密度、趋势和完整性 |
| 线上/线下销售 | `sales_metric_service.py` | 已按 `011` 拆分 | 第一阶段固定回归样本 |
| 门店与商品分析 | `/app/store`、`/app/product` | 已有部分销售、毛利、库存 | 第一阶段补齐比较、建议和下钻 |
| FIFO 库龄 | `command_center_service.py`、百胜入库同步 | 已接入但存在未知库龄 | 第一阶段补全入库来源和未知披露 |
| 库存预警 | `GET /inventory/warnings` | 已有预警表和转任务草稿 | 第一阶段扩展真实规则和证据 |
| VIP 资产 | `GET /member/assets/*` | 已有余额接口 | 第一阶段校准余额、负余额和交易下钻 |
| 任务状态机 | `/app/task`、`AppActionTask` | 已有确认、反馈、复查、关闭 | 第二阶段完善责任人与通知 |
| 利润分析 | `/app/finance/*` | 毛利存在，费用不完整 | 第二阶段接入费用后才计算经营利润 |
| AI 经营诊断 | `/app/ai-diagnosis/*` | 已有模块框架 | 第三阶段在数据门禁后启用自动建议 |
| 老板移动端 | `huabang-miniapp`、`backend/app/api/v1/mobile.py` | 有基础页面 | 第三阶段统一快照和任务接口 |

## 专题计划索引

- 百胜会员主档：`docs/superpowers/plans/2026-07-10-baison-member-sync.md`
- 百胜会员储值：`docs/superpowers/plans/2026-07-12-member-deposit-diagnosis.md`
- 百胜商品入库与 FIFO：`docs/superpowers/plans/2026-07-12-baison-product-diagnosis.md`
- AI 诊断各模块：`docs/superpowers/plans/2026-07-12-ai-diagnosis-all-modules.md`
- 经营总览线上/线下拆分：`docs/superpowers/plans/2026-07-13-dashboard-online-offline-sales.md`
- 经营中台浅色 UI：`docs/superpowers/plans/2026-07-14-command-center-light-ui.md`

本文件是阶段、依赖和验收的唯一总索引；专题计划负责具体子系统的代码级实施步骤。专题计划与本文件冲突时，以本文件的业务口径和阶段门禁为准。

---

# 第一阶段：可信经营结果与业务下钻

**阶段目标：** 完成老板经营首页、经营日报及业务下钻。老板每天可稳定查看昨日销售、实收、毛利、库存和 VIP 资产，能下钻到门店、款号、SKU、会员和原始流水；所有不完整数据明确披露。

## Task 1: 固化经营指标契约与数据质量状态

**Files:**
- Modify: `backend/app/services/sales_metric_service.py`
- Modify: `backend/app/services/command_center_service.py`
- Modify: `backend/app/models/dm.py`
- Modify: `backend/alembic/versions/e6f7a8b9c0d1_boss_command_center.py` only if migration has not reached production; otherwise create a new Alembic revision
- Modify: `backend/tests/test_command_center_contract.py`
- Modify: `backend/tests/test_sales_channel_split.py`

**Interfaces:**
- Consumes: 百胜小票、支付明细、成本明细、外穿衣物库存视图、会员主档。
- Produces: `MetricEnvelope(value, status, source, as_of, reason)` 语义及统一销售/实收/毛利字段。

- [ ] **Step 1: 为固定口径建立失败测试**

在 `backend/tests/test_command_center_contract.py` 增加固定样本，覆盖 VIP、POS、扫码、胜券扫、五月前储值、现金、线上支付、充值和退款；断言销售额与实收金额分别按全局口径计算，且 `total_sales = offline_sales + online_sales`。

- [ ] **Step 2: 验证测试先失败**

Run:

```bash
cd /srv/huabang-ai-center/backend
pytest -q tests/test_command_center_contract.py tests/test_sales_channel_split.py
```

Expected: 新增的不完整状态或固定口径断言失败，旧测试保持通过。

- [ ] **Step 3: 统一指标封装与来源字段**

在 `command_center_service.py` 中确保所有首页指标使用统一结构：

```python
{
    "value": 18100.0,
    "status": "ready",
    "source": "baison_pos",
    "as_of": "2026-07-13",
    "reason": None,
}
```

缺数时 `value` 为 `None`，状态为 `pending_data` 或 `stale`，不得以 `0` 代替。

- [ ] **Step 4: 扩展快照表并升级数据库**

补充线上/线下销售、实收、退货、成本覆盖率、库存未知库龄、VIP 正负余额、异常和任务数量、各来源更新时间字段。迁移必须有 `upgrade()` 和 `downgrade()`，并对 `report_date` 保持唯一约束。

- [ ] **Step 5: 运行契约和迁移测试**

```bash
cd /srv/huabang-ai-center/backend
pytest -q tests/test_command_center_contract.py tests/test_sales_channel_split.py
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: 测试通过，升级/回滚/再升级均成功，历史日报记录保留。

## Task 2: 完成每日 06:30 统一经营快照

**Files:**
- Modify: `backend/app/services/command_center_service.py`
- Modify: `backend/app/jobs/report_jobs.py`
- Modify: `scripts/generate_boss_command_center_daily.sh`
- Create or Modify: `backend/tests/test_command_center_daily_job.py`
- Modify: server user crontab

**Interfaces:**
- Consumes: 昨日销售、当日 05:30 后库存快照、会员同步后余额、规则结果。
- Produces: 一条幂等 `dm.dm_boss_daily_report` 记录、库存预警和待确认任务草稿。

- [ ] **Step 1: 编写重复执行测试**

同一 `report_date` 连续执行两次 `run_daily_command_center()`，断言日报只有一条、异常证据不重复、相同 `source_type + source_id` 的任务草稿只有一条。

- [ ] **Step 2: 实现事务锁和数据门禁**

沿用 PostgreSQL advisory lock；库存必须选择当日 `05:30` 后最新成功快照，会员必须选择最近一次完整同步。来源过期时仍生成日报，但对应指标标记 `stale` 并保留上次可信值。

- [ ] **Step 3: 固定调度时间**

crontab 使用服务器 UTC：

```cron
30 22 * * * /usr/bin/flock -n /tmp/huabang_boss_command_center.lock /srv/huabang-ai-center/scripts/generate_boss_command_center_daily.sh >> /srv/huabang-ai-center/logs/boss_command_center_daily.log 2>&1
```

- [ ] **Step 4: 验证幂等和日志**

```bash
cd /srv/huabang-ai-center/backend
pytest -q tests/test_command_center_daily_job.py tests/test_command_center_service.py
cd /srv/huabang-ai-center
scripts/generate_boss_command_center_daily.sh --date 2026-07-13
scripts/generate_boss_command_center_daily.sh --date 2026-07-13
```

Expected: 两次结果一致，无重复日报、异常或任务草稿，日志包含各数据源时间。

## Task 3: 完成老板首页与经营日报

**Files:**
- Modify: `backend/app/api/v1/dashboard.py`
- Modify: `backend/app/api/v1/report.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `frontend/src/views/dashboard/Index.vue`
- Modify: `frontend/src/views/report/Index.vue`
- Create or Modify: `frontend/tests/dashboard-command-center.test.cjs`
- Create or Modify: `frontend/tests/report-density.test.cjs`

**Interfaces:**
- Produces: 非破坏性扩展 `GET /dashboard/overview`、`GET /report/boss-daily/{date}`、`GET /report/boss-daily`。

- [ ] **Step 1: 固定 API 响应契约**

首页必须返回：经营结论、销售额、线上/线下销售、实收、订单、件数、客单价、连带率、折扣率、退货、毛利、库存、90/180 天库存、VIP 余额、VIP 销售、重大异常、今日行动及数据质量。

- [ ] **Step 2: 补全日报近 14 日字段**

近 14 日记录至少显示日期、销售额、实收、订单、件数、客单价、连带率、折扣率、退货率、毛利额、毛利率、成本状态和数据状态；点击日期切换完整日报。

- [ ] **Step 3: 调整首页信息顺序**

页面顺序固定为：昨日经营结论 -> 核心指标 -> 销售模块 -> 门店明细 -> 库存/VIP -> 数据质量 -> 重大异常与今日行动清单（底部）。不删除现有下钻入口。

- [ ] **Step 4: 应用浅色 UI 规范**

内容区 `#F5F7FA`，卡片白底、8px 圆角、浅边框；状态色低饱和。禁止深色内容块，表格排序图标与文字同排。

- [ ] **Step 5: 测试构建与桌面/移动验收**

```bash
cd /srv/huabang-ai-center/frontend
node --test tests/dashboard-command-center.test.cjs tests/report-density.test.cjs
npm run type-check
npm run build
```

Expected: 测试、类型检查和构建通过；桌面和 390px 移动视口无文字重叠及无控制横向溢出。

## Task 4: 完成门店经营质量分析

**Files:**
- Modify: `backend/app/api/v1/store.py`
- Modify: `frontend/src/views/store/Index.vue`
- Modify: `frontend/src/views/store/StoreOverview.vue`
- Create or Modify: `backend/tests/test_store_analysis.py`
- Create or Modify: `frontend/tests/store-analysis.test.cjs`

**Interfaces:**
- Produces: 门店汇总、趋势、商品、库存、VIP 与异常下钻字段；保留现有门店接口路径。

- [ ] **Step 1: 增加门店可信指标测试**

覆盖昨日销售、日环比、周同比、毛利、VIP 销售、库存金额、畅销款、滞销款和异常。客流、成交人数、试穿率、新老客、导购业绩无来源时必须返回 `pending_data`。

- [ ] **Step 2: 扩展门店聚合**

对销售、库存和 VIP 分别使用其业务日期，不把库存同步日期伪装为销售日期。每个指标返回来源和更新时间。

- [ ] **Step 3: 完成门店下钻**

门店行可进入门店详情；畅滞销款可进入款号/SKU；VIP 指标可进入会员列表；异常可进入证据或任务草稿。

- [ ] **Step 4: 验证 7 家销售门店范围**

```bash
cd /srv/huabang-ai-center/backend
pytest -q tests/test_store_analysis.py tests/test_sales_channel_split.py
```

Expected: 返回范围固定为 7 家销售门店，仓库不进入销售排行。

## Task 5: 完成商品决策与 FIFO 库龄

**Files:**
- Modify: `backend/app/integrations/baison/services/product_inbound_service.py`
- Modify: `backend/app/integrations/baison/services/product_transfer_inbound_service.py`
- Modify: `backend/app/api/v1/product.py`
- Modify: `backend/app/services/size_wall_service.py`
- Modify: `frontend/src/views/product/Index.vue`
- Modify: `frontend/src/views/product/SizeWall.vue`
- Modify: `backend/tests/test_product_inbound_service.py`
- Modify: `backend/tests/test_product_transfer_inbound_service.py`
- Create or Modify: `backend/tests/test_product_decision.py`

**Interfaces:**
- Produces: 单款销售、毛利、库存、动销、售罄、颜色/尺码结构及结构化建议。

- [ ] **Step 1: 补齐百胜入库和调拨到货历史**

按 10 编码库存范围回填可用历史，幂等写入入库批次。供应商、采购单、调拨来源存在时保留原始编号，无法匹配时进入库龄未知。

- [ ] **Step 2: 验证 FIFO 分摊**

测试销售先消耗老批次；现存库存从最近入库批次反向分摊；分摊总量等于当前库存；未知量独立列示。

- [ ] **Step 3: 形成结构化商品建议**

后端返回 `continue_sale`、`replenish`、`transfer`、`clearance` 四类建议之一，并返回规则证据。建议不得只返回自然语言。

- [ ] **Step 4: 完成款号/SKU/尺码墙下钻**

所有数量、金额、7 天销量和 7 天销售额支持排序；库存为 0 可筛除；排序图标与表头同排。

- [ ] **Step 5: 执行商品与库龄测试**

```bash
cd /srv/huabang-ai-center/backend
pytest -q tests/test_product_inbound_service.py tests/test_product_transfer_inbound_service.py tests/test_product_decision.py tests/test_size_wall_service.py
```

Expected: FIFO、建议、外穿衣物范围及无成本不计金额全部通过。

## Task 6: 完成库存预警与调拨/清仓证据

**Files:**
- Modify: `backend/app/services/command_center_service.py`
- Modify: `backend/app/api/v1/inventory.py`
- Modify: `frontend/src/views/inventory/Index.vue`
- Modify: `frontend/src/views/inventory/InventoryBalance.vue`
- Create or Modify: `backend/tests/test_inventory_warning_rules.py`
- Create or Modify: `frontend/tests/inventory-warning.test.cjs`

**Interfaces:**
- Produces: `GET /inventory/warnings`，支持日期、门店、类型、等级和任务状态筛选。

- [ ] **Step 1: 配置化库存规则**

覆盖 90/180 天、过季、断码、低动销高库存、有销量低库存、门店不均衡、可调拨、清仓和返仓；每条结果保存阈值、证据、来源和生成时间。

- [ ] **Step 2: 清理停滞规则结果**

使用幂等重算替换停留在 `2026-06-16` 的旧结果；保留历史日期快照，不直接物理删除审计证据。

- [ ] **Step 3: 保持任务草稿去重**

同一 `warning_date + store_code + product_code + sku_code + warning_type` 只生成一个活跃任务草稿。

- [ ] **Step 4: 验证仓库合计和库存金额**

10 个编码库存数量之和必须等于公司库存；无成本 SKU 数量保留、金额不计；页面显示成本覆盖率。

## Task 7: 完成 VIP 资产与销售分析

**Files:**
- Modify: `backend/app/api/v1/member.py`
- Modify: `backend/app/integrations/baison/services/member_service.py`
- Modify: `backend/app/integrations/baison/services/member_deposit_service.py`
- Modify: `frontend/src/views/member/Index.vue`
- Modify: `backend/tests/test_member_api.py`
- Modify: `backend/tests/test_baison_member_deposit_service.py`
- Create or Modify: `frontend/tests/member-assets.test.cjs`

**Interfaces:**
- Produces: `GET /member/assets/overview`、`/member/assets/list`、`/member/assets/transactions`。

- [ ] **Step 1: 校准会员主档余额**

以 `CZ_DQJE` 汇总当前余额；正余额、负余额、零余额分别统计。资产总额只汇总正余额，负余额输出异常人数、金额和会员下钻。

- [ ] **Step 2: 校准储值流水**

保持 `change_type=0` 为充值、`2` 为储值消费、`8` 为审计调整；充值不重复计入销售额。交易明细可追溯门店、会员、时间和原始单号。

- [ ] **Step 3: 增加 VIP 销售分析**

显示 VIP 销售额、占比、订单、件数、客单价、连带率、复购、门店排行、品类/款式、折扣、毛利、退货和充值消费转化率；缺少可靠字段时返回 `pending_data`。

- [ ] **Step 4: 保护会员隐私**

列表默认脱敏手机号；只有具备会员敏感字段权限的用户可查看完整联系方式，操作写入审计日志。

- [ ] **Step 5: 核对总额**

会员明细正余额合计必须等于首页 VIP 余额；10 编码外会员不得进入首期总额。

## Task 8: 第一阶段综合验收与上线门禁

**Files:**
- Modify: `backend/tests/test_command_center_contract.py`
- Create or Modify: `backend/tests/test_phase1_acceptance.py`
- Create: `docs/acceptance/boss-command-center-phase1.md`

- [ ] **Step 1: 固定验收日期和原始凭证**

选择至少 3 个业务日，保存百胜销售结算、库存、会员余额和入库记录的只读验收摘要；其中一天必须包含线上支付、充值或退款。

- [ ] **Step 2: 执行后端全量测试**

```bash
cd /srv/huabang-ai-center/backend
pytest -q
```

Expected: 全量通过；任何与口径相关的失败都阻止上线。

- [ ] **Step 3: 执行前端全量验证**

```bash
cd /srv/huabang-ai-center/frontend
node --test tests/*.test.cjs
npm run type-check
npm run build
```

Expected: 全部通过，产物生成到现有部署目录。

- [ ] **Step 4: 执行 Playwright 路由检查**

检查 `/app/dashboard`、`/app/report`、`/app/store`、`/app/product`、`/app/product/size-wall`、`/app/inventory`、`/app/member` 的桌面和移动视口；验证筛选、排序、分页、日期切换、下钻和导航。

- [ ] **Step 5: 完成第一阶段签字条件**

只有在销售/实收固定样本一致、库存合计一致、VIP 明细等于总额、日报幂等、来源时间可见、未知/待接入不冒充零值时，第一阶段标记完成。

---

# 第二阶段：异常稽核、利润与责任闭环

**阶段目标：** 将已验证的数据转化为可追溯异常、利润判断、VIP 分层和由负责人执行的任务；所有自动任务仍需人工确认。

## Task 9: 建立统一异常证据模型

**Files:**
- Create: `backend/alembic/versions/0b8c9d0e1f2a_business_exception_evidence.py`
- Create: `backend/app/services/exception_rule_service.py`
- Create: `backend/app/api/v1/audit.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `frontend/src/views/warning/Index.vue`
- Create: `backend/tests/test_exception_rule_service.py`

**Interfaces:**
- Produces: 异常主表、证据明细、规则版本及异常查询接口。

- [x] **Step 1: 定义异常唯一键和证据结构**

唯一键由 `business_date + rule_code + subject_type + subject_id + evidence_hash` 构成。证据保存原始业务表、原始单号、字段前后值、来源时间、规则阈值和规则版本。

- [x] **Step 2: 实现确定性规则**

覆盖退货、改单、折扣、会员、VIP 余额、充值、调拨、盘点和库存异常。导购、店长、抖音归属在来源不足时只记录 `pending_data`，不得推定责任人。

- [x] **Step 3: 增加异常下钻**

异常列表可进入门店、款号、SKU、会员、交易或原始单据；每个异常显示证据、口径、来源和生成时间。

- [x] **Step 4: 测试重算与规则版本**

同一规则重算不重复；规则阈值变化产生新版本但保留历史证据。

## Task 10: 接入完整费用并计算经营利润

**Files:**
- Modify: `backend/app/api/v1/finance.py`
- Modify: `backend/app/services/ai_diagnosis_service.py`
- Create or Modify: `backend/app/services/profit_service.py`
- Modify: `frontend/src/views/finance/FinanceOverview.vue`
- Modify: `frontend/src/views/finance/ExpenseAnalysis.vue`
- Create: `backend/tests/test_profit_service.py`

**Interfaces:**
- Consumes: 已核准销售成本、门店费用、总部费用、退货损失、清仓损失。
- Produces: 门店/商品/导购/VIP 毛利与经营利润，附费用覆盖率。

- [x] **Step 1: 建立费用来源清单和完整度测试**

明确租金、工资、社保、平台费、水电、物流、营销及其他费用的来源、粒度和归属规则。缺少任一必需费用时经营利润状态必须为 `pending_data`。

- [x] **Step 2: 实现利润聚合**

毛利与经营利润分开：毛利来自销售减商品成本；经营利润只在费用覆盖达到验收阈值且财务核准后计算。

- [x] **Step 3: 增加利润分析页面**

显示门店利润、单款利润、折扣损失、退货损失、清仓损失和库存占用资金；高销售低利润、VIP 折扣过高以规则异常展示。

- [x] **Step 4: 防止确定性误报**

测试费用缺失、成本覆盖不足、跨期费用和负销售等场景；任何不完整场景不得显示“盈利/亏损”确定结论。

**验收记录（2026-07-14）：** 八类费用、独立核准、公司/门店作用域、成本与费用门禁已完成；费用不完整时经营利润保持 `pending_data`。百胜退货金额已从小票结算负金额接入，`2026-07-06` 为 54 元、`2026-07-13` 为 0 元且均为 `ready`；缺少商品级退货成本时“退货损失”继续显示待接入，不以退货金额冒充损失。

## Task 11: 建立 VIP 分层、风险与唤醒名单

**Files:**
- Create: `backend/app/services/member_segment_service.py`
- Modify: `backend/app/api/v1/member.py`
- Modify: `frontend/src/views/member/Index.vue`
- Create: `backend/tests/test_member_segment_service.py`
- Create or Modify: `frontend/tests/member-segments.test.cjs`

**Interfaces:**
- Produces: 高价值、高余额、高复购、高客单、高毛利、沉睡、流失风险和可唤醒会员分层。

- [x] **Step 1: 配置化分层规则**

规则基于余额、RFM、毛利、最近消费日和复购频率；每个会员可属于多个标签，标签保存计算日期和证据。

- [x] **Step 2: 建立 VIP 风险规则**

覆盖大额余额长期未消费、高价值 VIP 90 天未到店、频率下降、充值后未二次消费、折扣过高、余额异常和退货异常。

- [x] **Step 3: 生成唤醒候选**

候选包含会员、归属门店、可确认责任人、联系理由、偏好品类/款式、建议商品和数据证据；责任归属不可靠时不自动指定导购。

- [x] **Step 4: 验证隐私和权限**

未经授权的用户不能导出完整手机号、余额或消费明细；导出和查看敏感数据均记录审计。

**验收记录（2026-07-14）：** 北京时间当天快照覆盖白名单注册门店内 11,643 名有效会员，连续两次重算均得到 11,016 名有标签会员、564 名风险会员和 550 名唤醒候选；人工确认的责任人字段在重算后保持不变。当前 POS 会员级历史不足 180 天，全部频率趋势保持 `pending_data`；会员商品成本覆盖不足，高毛利标签也保持 `pending_data`。页面按 `member:segment:view`、`member:sensitive:view`、`member:sensitive:export` 分级授权，未授权用户无法查看余额流水，旧会员档案、资产和回访接口的敏感字段也统一脱敏；敏感查看/导出写操作日志。退货异常的销售订单分母与退货订单均使用同一规则周期，指定无快照日期返回 `pending_data`。迁移已完成升级、回滚、再升级测试；后端全量 370 项通过、1 项跳过，前端 118 项通过，类型检查和生产构建通过。

## Task 12: 完成任务闭环和通知预算

**Files:**
- Modify: `backend/app/api/v1/task.py`
- Modify: `backend/app/models/app.py`
- Modify: `frontend/src/views/task/Index.vue`
- Modify: `frontend/src/views/task/Detail.vue`
- Modify: `backend/app/modules/dingtalk/runner.py`
- Create: `backend/app/services/task_notification_service.py`
- Create: `backend/tests/test_task_workflow.py`
- Create: `backend/tests/test_task_notification_budget.py`

**Interfaces:**
- Produces: 草稿 -> 确认派发 -> 反馈 -> 复查 -> 关闭，及逾期提醒。

- [x] **Step 1: 固定状态机权限**

草稿只有老板/主管可确认；负责人可反馈；复查人可通过或退回；关闭需保留完整记录，禁止直接跨状态。

- [x] **Step 2: 补齐任务字段**

任务包含负责人、截止时间、处理要求、证据、上传结果、反馈记录、复查意见、老板确认、逾期状态和来源异常。

- [x] **Step 3: 接入钉钉/企业微信通知**

通知失败不得改变任务状态。钉钉每日 API 总预算为 160 次，通讯录、考勤、审批和任务通知共享预算并记录实际消耗；接近预算时优先保留任务派发和逾期提醒。

- [x] **Step 4: 验证去重和并发**

同一异常不重复建任务；重复确认、重复反馈和并发复查均保持幂等。

**验收记录（2026-07-14）：** 任务状态机已固定为“草稿、派发、反馈、复查、关闭”，负责人和责任角色均按启用角色及数据范围授权；普通导购只看到本人或本人门店内匹配角色的任务，部门主管写操作也不能越过本部门范围。任务派发与逾期通知改为按收件人持久化的数据库发件箱，使用行锁、单调 claim 代际和稳定事件键阻止并发重复发送；部分收件人失败时只续发失败人，状态不明的旧发送进入人工确认，超过 5 次后仅允许主管执行带审计的人工重试。钉钉通讯录、考勤、审批和任务通知共用北京时间每日 160 次预算，其中 20 次保留给派发和逾期通知。真实 PostgreSQL 验证已覆盖角色任务可见、部分失败续发、派发与逾期事件隔离、并发不重复、状态不明隔离和稳定事件键；迁移已完成旧任务状态、既有权限元数据和迁移新增权限均可恢复的升级、回滚、再升级测试。后端全量 416 项通过、1 项跳过，前端 122 项通过，类型检查和生产构建通过。

## Task 13: 第二阶段综合验收

**Files:**
- Create: `backend/tests/test_phase2_acceptance.py`
- Create: `docs/acceptance/boss-command-center-phase2.md`

- [ ] **Step 1: 验证异常证据链**

每类已启用异常至少抽查 3 条，能够从异常下钻到原始业务记录，规则和阈值可解释。

状态：自动化证据契约已通过；真实规则不足 3 条或未触发的部分仍待老板按验收记录人工抽查。

- [ ] **Step 2: 验证利润门禁**

费用完整时与财务核准表一致；费用不完整时只显示毛利和缺失来源，不显示经营利润结论。

状态：费用不完整门禁已通过；当前费用覆盖率不足，仍待财务核准表和老板签字。

- [ ] **Step 3: 验证 VIP 分层与任务闭环**

抽查分层证据，完成一条 VIP 唤醒任务从草稿到关闭的全流程，并验证通知失败不丢任务。

状态：分层、状态机和通知失败隔离已自动验证；真实 VIP 唤醒任务全流程仍待老板选样签字。

- [x] **Step 4: 运行全量测试和迁移回滚**

```bash
cd /srv/huabang-ai-center/backend
pytest -q
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: 全量通过，历史异常、任务和会员标签可恢复。

---

# 第三阶段：AI 决策、归属稽核与老板移动端

**阶段目标：** 在第一、二阶段可信数据和规则之上生成经营结论、自动建议和行动清单，并让老板在移动端完成查看、确认和复查。

## Task 14: 建立受约束的 AI 经营结论服务

**Files:**
- Modify: `backend/app/services/ai_engine.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/services/ai_diagnosis_service.py`
- Modify: `backend/app/api/v1/ai_diagnosis.py`
- Modify: `frontend/src/views/diagnosis/Index.vue`
- Create: `backend/tests/test_ai_command_center_guardrails.py`

**Interfaces:**
- Consumes: 经营快照、确定性规则、异常证据、任务状态、数据质量。
- Produces: 日/周/月经营摘要、门店/商品/库存/VIP 建议和行动清单草稿。

- [x] **Step 1: 建立 AI 输入白名单**

只传入已授权、带来源和状态的结构化指标。`pending_data` 不参与数值结论，`estimated` 必须在输出中明确标注。

- [x] **Step 2: 建立输出结构和禁语测试**

输出分为 `facts`、`risks`、`recommendations`、`actions`、`limitations`。费用不完整时禁止出现“公司盈利/亏损”等确定性表述。

- [x] **Step 3: 提供模板回退**

模型超时、限流或返回非法结构时使用模板摘要；日报、规则和任务草稿仍正常生成。

- [x] **Step 4: 生成人工可确认行动**

AI 建议不得直接派发任务、修改价格、发起调拨、清仓、营销或联系会员；只能形成待确认建议或任务草稿。

## Task 15: 完成业绩归属稽核

**Files:**
- Create: `backend/app/services/performance_attribution_service.py`
- Modify: `backend/app/api/v1/audit.py`
- Modify: `frontend/src/views/warning/Index.vue`
- Create: `backend/tests/test_performance_attribution.py`

**Interfaces:**
- Consumes: 抖音来源、门店交易、会员归属、导购排班、改单日志、跨店消费和退款记录。
- Produces: 归属建议、冲突证据和人工裁决记录。

- [x] **Step 1: 先建立数据可用性门禁**

任一来源缺失时返回 `pending_data`，不得根据会员历史或当前门店单方面判定归属。

- [x] **Step 2: 实现可配置归属规则**

覆盖抖音客户、老会员复购、VIP 充值、VIP 消费、跨店消费、退货冲销和人工改单；规则必须版本化。

- [x] **Step 3: 保留人工裁决**

冲突只生成稽核项；老板/主管裁决后保存裁决人、时间、理由和证据，不回写篡改原始交易。

- [x] **Step 4: 验证虚报、重复报和改归属**

固定样本覆盖重复申报、同单多人申报、店长改单和跨店会员，确保可追溯且不误判。

**2026-07-14 验收记录：** 门店交易、跨店历史和退款记录已能通过完整百胜同步批次判定就绪；抖音订单级绑定、责任导购、门店排班和改单日志仍按 `pending_data` 展示，不自动归责。归属规则已版本化，覆盖抖音、老客复购、VIP 充值/消费、跨店、退款冲销和改单冲突；人工裁决仅写异常审计快照并保留历史，不修改原始交易。后端全量 `454 passed, 1 skipped`，前端 `124 passed`，类型检查和生产构建通过。

## Task 16: 完成 VIP 资产管理行动系统

**Files:**
- Create: `backend/app/services/member_action_service.py`
- Modify: `backend/app/api/v1/member.py`
- Modify: `backend/app/api/v1/task.py`
- Modify: `frontend/src/views/member/Index.vue`
- Modify: `frontend/src/views/task/Detail.vue`
- Create: `backend/tests/test_member_action_service.py`

**Interfaces:**
- Produces: 每日 VIP 行动清单、推荐商品、建议话术、跟进结果和复购归因。

- [ ] **Step 1: 生成会员行动候选**

基于已验证的会员分层、偏好、余额和最近消费生成候选，包含联系理由、推荐商品和数据依据。

- [ ] **Step 2: 人工确认责任人和话术**

原导购和归属可信时可预填；否则由主管选择。任何联系动作前必须人工确认。

- [ ] **Step 3: 记录跟进闭环**

保存是否联系、是否到店、是否成交、成交金额、未成交原因和下次跟进时间；与任务状态机复用，不建第二套任务表。

- [ ] **Step 4: 评估行动效果**

区分自然复购与行动后复购，不把时间相邻直接当因果；输出触达率、到店率和成交率。

## Task 17: 完成老板移动端看板

**Files:**
- Modify: `backend/app/api/v1/mobile.py`
- Modify: `huabang-miniapp/huabang-miniapp/app.js`
- Modify: `huabang-miniapp/huabang-miniapp/app.json`
- Modify: `huabang-miniapp/huabang-miniapp/pages/dashboard/index.js`
- Modify: `huabang-miniapp/huabang-miniapp/pages/dashboard/index.wxml`
- Modify: `huabang-miniapp/huabang-miniapp/pages/dashboard/index.wxss`
- Modify: `huabang-miniapp/huabang-miniapp/pages/alerts/index.js`
- Modify: `huabang-miniapp/huabang-miniapp/pages/alerts/index.wxml`
- Modify: `huabang-miniapp/huabang-miniapp/pages/inventory/index.js`
- Modify: `huabang-miniapp/huabang-miniapp/pages/inventory/index.wxml`
- Modify: `huabang-miniapp/huabang-miniapp/pages/profile/index.js`
- Modify: `huabang-miniapp/huabang-miniapp/pages/profile/index.wxml`
- Create or Modify: `backend/tests/test_mobile_command_center.py`
- Create or Modify: miniapp component tests

**Interfaces:**
- Consumes: 与 Web 端相同的经营快照、异常和任务接口。
- Produces: 移动端经营摘要、重大异常、今日行动、任务确认和复查。

- [ ] **Step 1: 复用统一指标契约**

移动端不得另算销售、实收、毛利、库存或 VIP；只做适配和格式化。

- [ ] **Step 2: 完成 30 秒首页**

首屏显示经营结论、销售、实收、毛利状态、库存、VIP 余额、重大异常数和待确认任务；“我的”入口置于右上角，底部导航为首页、销售、库存、财务、人事。

- [ ] **Step 3: 完成任务确认与复查**

老板可查看证据、确认派发、复查反馈和关闭；所有操作与 Web 端权限及审计一致。

- [ ] **Step 4: 验证小屏和弱网**

在 320px、375px、390px 宽度检查文字和卡片；接口失败显示最近成功时间和过期状态，不显示伪造零值。

## Task 18: 第三阶段与全项目最终验收

**Files:**
- Create: `backend/tests/test_phase3_acceptance.py`
- Create: `docs/acceptance/boss-command-center-final.md`
- Modify: project operations runbook

- [ ] **Step 1: 验证 AI 安全边界**

注入缺费用、缺客流、过期库存和模型不可用场景，确认 AI 不编造、不越权、模板回退正常。

- [ ] **Step 2: 验证归属稽核和 VIP 行动**

从异常/会员候选开始，完成证据查看、人工确认、任务派发、反馈、复查和关闭，并保留完整审计链。

- [ ] **Step 3: 验证 Web 与移动一致性**

同一业务日的销售、实收、库存、VIP、异常数和任务数在 Web 与移动端一致；允许的差异仅为显示精度。

- [ ] **Step 4: 执行全量技术验收**

```bash
cd /srv/huabang-ai-center/backend
pytest -q
alembic upgrade head
cd /srv/huabang-ai-center/frontend
node --test tests/*.test.cjs
npm run type-check
npm run build
```

Expected: 全部通过；Playwright 桌面/移动截图无重叠、空白主区或导航死链。

- [ ] **Step 5: 执行生产抽查和回滚演练**

抽查首页、日报、门店、商品、库存、会员、异常、任务、AI 与移动接口；确认定时任务日志、监控和告警可用，并完成一次数据库迁移及前端版本回滚演练。

- [ ] **Step 6: 最终业务签字**

老板可在 30 秒内回答：昨天经营结果如何、哪些数据是预估或缺失、当前最大风险是什么、今天谁负责处理；任一问题无法回答则本计划未完成。

---

## 阶段门禁与发布顺序

1. 第一阶段未通过销售、库存、VIP 和来源时间验收，不得发布第二阶段利润或责任结论。
2. 第二阶段未完成费用完整度、异常证据和任务闭环，不得发布第三阶段自动经营建议。
3. AI、通知和移动端故障不得阻断基础经营快照、日报、规则和任务数据。
4. 每阶段先在测试数据和固定验收日验证，再在生产只读抽查，最后开放写操作。
5. 每阶段发布后观察至少一个完整北京时间日周期，确认同步、06:30 日报和任务去重后再进入下一阶段。

## 最终完成定义

- **看得懂：** 首页和日报对每个指标显示数值、状态、来源、业务日期和限制说明。
- **查得出：** 销售、库存、VIP、异常和任务都能下钻到可核验的业务明细或原始单号。
- **推得动：** 重大风险可生成去重草稿，经人工确认后进入负责人、截止时间、反馈、复查和关闭闭环。
- **不误导：** 缺失不显示为零，预估不显示为真实，费用不全不判断净利润，AI 不替代确定性规则或人工授权。
- **可运营：** 定时任务幂等、失败保留可信数据、日志可查、部署可回滚、桌面和移动端指标一致。
