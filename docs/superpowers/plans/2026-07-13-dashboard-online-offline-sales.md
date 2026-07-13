# 经营总览线上/线下销售拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按百胜结算代码 `011` 将经营总览销售额拆成线上销售与线下销售，同时保持总销售额不变。

**Architecture:** 在共享 `PAY_DETAIL_SQL` 中一次性产出总销售、线上销售、线下销售，再由经营总览与趋势接口复用。前端只消费后端明确字段，不自行推导渠道金额。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL JSONB、Vue 3、TypeScript、Node test、pytest。

## Global Constraints

- `011`“线上支付”计线上销售。
- `000`、`003`、`004`、`666`、`971`计线下销售。
- `总销售额 = 线下销售 + 线上销售`。
- 保持门店白名单、作废单、挂单和退款规则不变。
- 线上销售为零时显示真实 `¥0`，不显示待接入。
- 不改动服务器上与本需求无关的未提交文件。

---

### Task 1: 共享支付口径产出渠道金额

**Files:**
- Modify: `backend/app/services/sales_metric_service.py`
- Create: `backend/tests/test_sales_channel_split.py`

**Interfaces:**
- Produces: `PAY_DETAIL_SQL`列 `sales_amount`、`offline_sales_amount`、`online_sales_amount`。
- Invariant: `sales_amount = offline_sales_amount + online_sales_amount`。

- [ ] **Step 1: Write the failing test**

测试使用临时 PostgreSQL 查询片段或静态 SQL 契约，断言 `011`只出现在 `online_sales_amount`条件中，其他五个有效代码出现在 `offline_sales_amount`条件中，并断言总销售代码集合为两者并集。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_sales_channel_split.py`

Expected: FAIL，因为 `PAY_DETAIL_SQL`尚未输出两个渠道列。

- [ ] **Step 3: Write minimal implementation**

在 `PAY_DETAIL_SQL` 中增加：

```sql
SUM(CASE WHEN p->>'jsdm' IN ('000','003','004','666','971') AND amount > 0 THEN amount ELSE 0 END) AS offline_sales_amount,
SUM(CASE WHEN p->>'jsdm' = '011' AND amount > 0 THEN amount ELSE 0 END) AS online_sales_amount
```

保留现有 `sales_amount`、实收和退款表达式。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_sales_channel_split.py`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sales_metric_service.py backend/tests/test_sales_channel_split.py
git commit -m "feat: split Baison sales by payment channel"
```

### Task 2: 经营总览与趋势返回真实渠道金额

**Files:**
- Modify: `backend/app/services/business_overview_service.py`
- Modify: `backend/app/api/v1/dashboard.py`
- Modify: `backend/tests/test_sales_channel_split.py`

**Interfaces:**
- Consumes: `PAY_DETAIL_SQL.offline_sales_amount`和 `PAY_DETAIL_SQL.online_sales_amount`。
- Produces: `business_metrics.yesterday_offline_sales`、`business_metrics.yesterday_online_sales`。
- Produces: 趋势行 `total_sales`、`offline_sales`、`online_sales`。

- [ ] **Step 1: Write failing overview and trend tests**

断言服务初始化两个非待接入渠道指标；DWD查询使用共享支付拆分；趋势SQL分别求和两列，且返回值不再固定 `online_sales: 0`。

- [ ] **Step 2: Run tests to verify expected failures**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_sales_channel_split.py`

Expected: FAIL，缺少业务指标字段且趋势仍把全部销售归为线下。

- [ ] **Step 3: Implement overview metrics**

`business_metrics`加入：

```python
"yesterday_offline_sales": _pending("销售渠道尚未拆分"),
"yesterday_online_sales": _pending("销售渠道尚未拆分"),
```

单日 DWD 查询通过 `PAY_DETAIL_SQL`汇总两个渠道，并用 `_value(..., 2)`写入，即使值为零也保持 ready。`platform_sales`使用相同金额构造。

- [ ] **Step 4: Implement trend aggregation**

趋势 SQL 增加：

```sql
COALESCE(SUM(pay.offline_sales_amount), 0) offline_sales,
COALESCE(SUM(pay.online_sales_amount), 0) online_sales
```

响应直接读取这两列，并保留 `total_sales`。

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_sales_channel_split.py tests/test_command_center_contract.py`

```bash
git add backend/app/services/business_overview_service.py backend/app/api/v1/dashboard.py backend/tests/test_sales_channel_split.py
git commit -m "feat: expose dashboard sales channel split"
```

### Task 3: 前端卡片、回归、部署与真实数据核对

**Files:**
- Modify: `frontend/src/views/dashboard/Index.vue`
- Create: `frontend/tests/dashboard-sales-channel.test.cjs`

**Interfaces:**
- Consumes: `business_metrics.yesterday_offline_sales`和 `business_metrics.yesterday_online_sales`。
- Displays: 顶部总销售、线下销售、线上销售；销售模块渠道卡；真实两条趋势线。

- [ ] **Step 1: Write failing frontend contract test**

断言页面包含“线下销售”“线上销售”，并从两个新业务指标取值，而不是用总额相减。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/dashboard-sales-channel.test.cjs`

Expected: FAIL，顶部 API 卡片尚未消费新字段。

- [ ] **Step 3: Implement frontend cards**

在 `apiCards`加入：

```ts
{ label: "线下销售", value: moneyMetric("business_metrics", "yesterday_offline_sales"), note: "百胜非011结算", tone: "orange" },
{ label: "线上销售", value: moneyMetric("business_metrics", "yesterday_online_sales"), note: "百胜011线上支付", tone: "blue" },
```

`channelCards`改为直接读取同一指标，保留销售件数卡；趋势图继续消费接口的真实 `offline_sales`与 `online_sales`。

- [ ] **Step 4: Run full verification**

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_sales_channel_split.py tests/test_command_center_contract.py
cd ../frontend && node --test tests/*.test.cjs && npm run build
```

Expected: 全部 PASS，Vite build成功。

- [ ] **Step 5: Deploy and verify live data**

合并到 `/srv/huabang-ai-center`，构建 `frontend/dist`，重启后端服务；查询最新业务日，确认 `total = offline + online`，并在 `/app/dashboard`核对卡片和趋势。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/dashboard/Index.vue frontend/tests/dashboard-sales-channel.test.cjs
git commit -m "feat: show online and offline sales on dashboard"
```
