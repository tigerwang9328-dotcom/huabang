# Mumaren Finance Book Sync and Contract Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep one selected ledger across the finance center and make the reported finance pages use the deployed API contracts.

**Architecture:** A frontend composable owns the selected valid book ID and persists it in browser storage. Existing pages bind their selectors to that composable. The backend exposes active tax types per book; frontend types and views send and render only server-defined fields.

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus, FastAPI, SQLAlchemy, pytest, Node test runner.

## Global Constraints

- All finance data remains isolated by `book_id`.
- Write flows remain draft-only; no automatic review, posting, or voucher creation.
- Do not alter unrelated dirty-worktree files.

---

### Task 1: Shared selected-book state

**Files:**
- Create: `frontend/src/composables/useMumarenFinanceBook.ts`
- Modify: finance center Vue views that render `选择独立账簿`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: Write failing static regression tests**

```js
assert.match(composable, /localStorage/)
assert.match(composable, /selectedBookId/)
assert.match(invoiceView, /useMumarenFinanceBook/)
```

- [ ] **Step 2: Run the Node test and verify it fails**

Run: `node --test tests/mumaren-finance-center.test.cjs`

- [ ] **Step 3: Implement the composable and bind each finance page**

```ts
const selectedBookId = ref<number>()
const selectBook = (id?: number) => { selectedBookId.value = id; localStorage.setItem(KEY, String(id ?? "")) }
```

Each page uses the shared `bookId`, validates it against loaded books, and calls its existing load routine after selection.

- [ ] **Step 4: Re-run the Node test**

Run: `node --test tests/mumaren-finance-center.test.cjs`

### Task 2: Repair reported CRUD contracts

**Files:**
- Modify: `frontend/src/api/mumarenFinanceCenter.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceInvoices.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceCashierAccounts.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceCashierReconciliation.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceSettingsAuxiliary.vue`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: Write failing contract tests**

```js
assert.match(api, /invoice_type/)
assert.match(api, /account_code/)
assert.match(api, /cash_account_id/)
assert.match(api, /parent_id/)
```

- [ ] **Step 2: Run test and verify it fails**

Run: `node --test tests/mumaren-finance-center.test.cjs`

- [ ] **Step 3: Align types, payloads and displays to FastAPI models**

Use the deployed model names exactly: invoice `invoice_no/invoice_type/counterparty_name`; cash account `account_code/account_type/currency`; flow `flow_date/in|out/category/counterparty_name`; reconciliation `cash_account_id/period/adjusted_balance`; auxiliary `parent_id/is_active` and standard dimensions.

- [ ] **Step 4: Run test and frontend build**

Run: `node --test tests/mumaren-finance-center.test.cjs && npm run build`

### Task 3: Tax type list and dropdown

**Files:**
- Modify: `backend/app/api/v1/mumaren_finance_center_domains.py`
- Modify: `frontend/src/api/mumarenFinanceCenter.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceTax.vue`
- Test: `backend/tests/test_mumaren_finance_center_tax_types.py`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] **Step 1: Write failing backend and frontend tests**

```python
response = await client.get('/api/v1/finance-center/mumaren/tax-types?book_id=1')
assert response.status_code == 200
```

```js
assert.match(taxView, /taxTypesApi\.list/)
assert.match(taxView, /el-select v-model="form.tax_type_id"/)
```

- [ ] **Step 2: Run tests and verify expected failures**

Run: `pytest -q tests/test_mumaren_finance_center_tax_types.py && node --test tests/mumaren-finance-center.test.cjs`

- [ ] **Step 3: Add active tax-type endpoint and bind select**

```python
@router.get('/tax-types')
async def list_tax_types(book_id: int = Query(ge=1), ...):
    return ApiResponse.ok(data=...)
```

The Vue dialog loads tax types for the selected book and prevents submission until a real option is selected.

- [ ] **Step 4: Run focused backend/frontend tests, build, and deploy**

Run: `pytest -q tests/test_mumaren_finance_center_tax_types.py && node --test tests/mumaren-finance-center.test.cjs && npm run build`

Restart only the backend after its tests pass; static frontend deployment is the completed build output.
