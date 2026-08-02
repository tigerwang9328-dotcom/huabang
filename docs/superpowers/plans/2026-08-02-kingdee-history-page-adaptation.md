# 金蝶历史账簿页面适配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让三套已迁入金蝶账簿在财务中心的所有页面准确呈现历史数据或明确的来源缺失状态。

**Architecture:** 页面只以 `useMumarenFinanceBook` 提供的账簿 ID 读取独立 schema。可从历史凭证、分录、余额快照和已导入领域表获得的数据走只读 API；没有对应来源表的数据由统一只读缺失状态承载。

**Tech Stack:** Vue 3、TypeScript、Element Plus、FastAPI、SQLAlchemy、PostgreSQL、pytest、Node test。

## Global Constraints

- 金蝶历史账簿永久只读；不调用写接口。
- 不改写 `fin_*`、旧财务或金蝶来源数据库。
- 每个请求必须以 `book_id` 隔离，并忽略切换账簿后的旧响应。
- 空结果仅在确认该账簿没有该类已迁入事实时展示；不能伪造零值。

---

### Task 1: 建立页面-来源适配矩阵与统一缺失状态

**Files:**
- Modify: `frontend/src/config/financeCenterModules.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinancePlaceholder.vue`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: 写失败测试**

```js
assert.match(source, /历史来源未迁入/)
assert.doesNotMatch(source, /新增|保存|删除/)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `node --test frontend/tests/mumaren-finance-center.test.cjs`
Expected: 缺少历史来源状态断言。

- [ ] **Step 3: 实现最小缺失状态**

```ts
availability: "historical_source_unavailable"
unavailableReason: "该类历史来源未迁入；历史凭证、余额快照和报表不受影响。"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `node --test frontend/tests/mumaren-finance-center.test.cjs`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/config/financeCenterModules.ts frontend/src/views/mumaren-finance-center/MumarenFinancePlaceholder.vue frontend/tests/mumaren-finance-center.test.cjs
git commit -m "fix(finance): clarify unavailable Kingdee history sources"
```

### Task 2: 补齐可由历史凭证和余额快照支持的只读页面

**Files:**
- Modify: `backend/app/api/v1/mumaren_finance_center.py`
- Modify: `frontend/src/api/mumarenFinanceCenter.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceLedgers.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceLedgerDetail.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceReportTrialBalance.vue`
- Test: `backend/tests/test_mumaren_finance_center_reports.py`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: 写失败测试**

```python
def test_history_book_report_reads_only_its_posted_vouchers():
    assert report["book_id"] == history_book.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_mumaren_finance_center_reports.py -q`
Expected: 缺少历史账簿报表覆盖。

- [ ] **Step 3: 实现只读查询**

```python
statement = statement.where(FinanceCenterMumarenVoucher.book_id == book_id)
if book.is_readonly:
    statement = statement.where(FinanceCenterMumarenVoucher.is_readonly.is_(True))
```

- [ ] **Step 4: 运行后端与前端测试**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_mumaren_finance_center_reports.py -q; node --test frontend/tests/mumaren-finance-center.test.cjs`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/mumaren_finance_center.py backend/tests/test_mumaren_finance_center_reports.py frontend/src/api/mumarenFinanceCenter.ts frontend/src/views/mumaren-finance-center/MumarenFinanceLedgers.vue frontend/src/views/mumaren-finance-center/MumarenFinanceLedgerDetail.vue frontend/src/views/mumaren-finance-center/MumarenFinanceReportTrialBalance.vue frontend/tests/mumaren-finance-center.test.cjs
git commit -m "feat(finance): adapt historical ledger pages"
```

### Task 3: 接入应收应付和税务的已迁入只读事实

**Files:**
- Modify: `backend/app/api/v1/mumaren_finance_center_domains.py`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceArAp.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceArApAging.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceTax.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceTaxRecords.vue`
- Test: `backend/tests/test_mumaren_finance_center_domains.py`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: 写失败测试**

```python
def test_domains_reject_cross_book_history_query():
    assert response.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_mumaren_finance_center_domains.py -q`
Expected: 缺少历史账簿域数据隔离断言。

- [ ] **Step 3: 实现只读来源状态**

```ts
const readOnlyMessage = "金蝶迁移账簿只读；该类历史来源未迁入时不提供新增或结算。";
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_mumaren_finance_center_domains.py -q; node --test frontend/tests/mumaren-finance-center.test.cjs`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/mumaren_finance_center_domains.py backend/tests/test_mumaren_finance_center_domains.py frontend/src/views/mumaren-finance-center/MumarenFinanceArAp.vue frontend/src/views/mumaren-finance-center/MumarenFinanceArApAging.vue frontend/src/views/mumaren-finance-center/MumarenFinanceTax.vue frontend/src/views/mumaren-finance-center/MumarenFinanceTaxRecords.vue frontend/tests/mumaren-finance-center.test.cjs
git commit -m "feat(finance): adapt historical receivable and tax pages"
```

### Task 4: 验收、构建和上线核验

**Files:**
- Test: `backend/tests/test_mumaren_finance_center_*.py`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: 运行全量针对性测试**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_mumaren_finance_center_*.py -q; node --test frontend/tests/mumaren-finance-center.test.cjs`
Expected: PASS。

- [ ] **Step 2: 类型检查和构建**

Run: `npm run type-check; npm run build`
Expected: 两项成功。

- [ ] **Step 3: 浏览器验收**

```text
依次选择三套历史账簿，验证凭证、科目余额、明细账、三张报表、应收应付、税务与余额快照；确认只读按钮禁用或来源缺失说明准确。
```

- [ ] **Step 4: 发布后健康检查**

Run: `curl -fsS http://127.0.0.1:8000/health`
Expected: `status=ok`，数据库和 Redis 均连接。
