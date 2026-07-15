# Standard Purchase Price Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every user-visible and analytical cost-price input with the Baison SKU `marketPrice` standard purchase price, then recompute inventory, sales, margin, estimated operating profit, and AI diagnosis consistently.

**Architecture:** Add an explicit `dim.dim_sku.standard_purchase_price` column and a canonical SKU standard-price view, populate it from the existing Baison `marketPrice`, and make every current consumer join that canonical source. Preserve legacy columns only for rollback compatibility; calculations expose source, coverage, and missing-price status. Estimated operating profit remains guarded: it is displayed from gross profit less known expenses, but only complete approved data is `ready` or eligible for definitive AI/rule conclusions.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL 16, Alembic, pytest, Vue 3, TypeScript, Element Plus, Node.js native test runner, Vite, Playwright.

## Global Constraints

- Standard purchase price source is exactly Baison SKU `marketPrice`.
- Do not fall back to `cbj`, legacy product cost, or last purchase price when standard purchase price is missing.
- Keep the `GY1229` one-yuan sentinel rule: sales cost is 60% of sales; inventory value remains quantity times one yuan.
- Existing API routes remain stable; legacy fields may remain for compatibility but frontend code must stop consuming them.
- Missing standard purchase price never becomes zero-cost `ready` data.
- Price values require the product sensitive-field permission; unauthorized users receive no amount.
- No Baison API call is required for the migration or historical rebuild.
- All user-visible labels use “标准进价”, not “成本价”.

---

### Task 1: Add the canonical standard purchase price field

**Files:**
- Create: `backend/alembic/versions/233e6f708192_standard_purchase_price.py`
- Modify: `backend/app/models/dim.py`
- Modify: `backend/app/api/v1/system.py`
- Test: `backend/tests/test_standard_purchase_price_schema.py`

**Interfaces:**
- Produces: `DimSku.standard_purchase_price: Numeric(12, 2) | None`.
- Produces: PostgreSQL view `dim.v_baison_sku_standard_purchase_price` with `sku_code`, `product_code`, `color_code`, `size_code`, `standard_purchase_price`, `source_name`, and `synced_at`.
- Produces: field resource `product.standard_purchase_price` labelled `商品标准进价`.

- [ ] **Step 1: Write the failing schema tests**

```python
def test_dim_sku_exposes_standard_purchase_price():
    assert "standard_purchase_price" in DimSku.__table__.columns

def test_migration_backfills_from_market_price_and_defines_view():
    text = Path("alembic/versions/233e6f708192_standard_purchase_price.py").read_text()
    assert "NULLIF(market_price, 0)" in text
    assert "v_baison_sku_standard_purchase_price" in text
    assert "product.standard_purchase_price" in text
```

- [ ] **Step 2: Run the schema tests and verify RED**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_schema.py`

Expected: FAIL because the model column and migration do not exist.

- [ ] **Step 3: Add the model column and migration**

Implement the model column:

```python
standard_purchase_price = Column(
    Numeric(12, 2),
    comment="百胜SKU marketPrice标准进价",
)
```

The migration must:

```sql
ALTER TABLE dim.dim_sku ADD COLUMN standard_purchase_price numeric(12,2);
UPDATE dim.dim_sku
SET standard_purchase_price = NULLIF(market_price, 0)
WHERE source_system = 'baison';

CREATE VIEW dim.v_baison_sku_standard_purchase_price AS
SELECT sku_code, product_code,
       COALESCE(BTRIM(color_code::text), '') AS color_code,
       COALESCE(BTRIM(size_code::text), '') AS size_code,
       NULLIF(standard_purchase_price, 0) AS standard_purchase_price,
       'baison_sku.marketPrice'::text AS source_name,
       synced_at
FROM dim.dim_sku
WHERE source_system='baison';
```

Copy existing `product.cost_price` field permissions to `product.standard_purchase_price`. The new field is migration-owned: upgrade inserts target rows idempotently, and downgrade removes all `product.standard_purchase_price` permission rows before dropping the view and column.

- [ ] **Step 4: Rename the system field resource label**

Replace the product field resource with:

```python
("product", "product.standard_purchase_price", "商品标准进价")
```

Keep permission lookup backward-compatible with existing copied rows during the deployment window.

- [ ] **Step 5: Run tests and migration round trip**

Run:

```bash
cd backend
/srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_schema.py
/srv/huabang-ai-center/backend/.venv/bin/alembic upgrade head
/srv/huabang-ai-center/backend/.venv/bin/alembic downgrade 222d5e6f7081
/srv/huabang-ai-center/backend/.venv/bin/alembic upgrade head
```

Expected: tests pass and all three Alembic commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/233e6f708192_standard_purchase_price.py backend/app/models/dim.py backend/app/api/v1/system.py backend/tests/test_standard_purchase_price_schema.py
git commit -m "feat: add canonical standard purchase price"
```

---

### Task 2: Populate standard purchase price from Baison SKU sync

**Files:**
- Modify: `backend/app/integrations/baison/services/sku_service.py`
- Modify: `backend/app/api/v1/product.py`
- Test: `backend/tests/test_baison_standard_purchase_price.py`

**Interfaces:**
- Consumes: `DimSku.standard_purchase_price` from Task 1.
- Produces: `_dim_row(raw)["standard_purchase_price"]` from `raw["marketPrice"]`.
- Produces: quality fields `sku_missing_standard_purchase_price_count`, `sku_standard_purchase_price_ready_count`, and `sku_standard_purchase_price_rate`.

- [ ] **Step 1: Write failing mapping and quality tests**

```python
def test_sku_market_price_maps_to_standard_purchase_price():
    row = _dim_row({"sku": "A-00M", "goodsSn": "A", "marketPrice": "80"}, NOW)
    assert row["standard_purchase_price"] == Decimal("80")

def test_zero_market_price_is_missing_standard_purchase_price():
    row = _dim_row({"sku": "A-00M", "goodsSn": "A", "marketPrice": "0"}, NOW)
    assert row["standard_purchase_price"] is None
```

Add an API contract test asserting the new quality fields are returned and the old missing-cost count is not used by new frontend code.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_baison_standard_purchase_price.py`

Expected: FAIL because `_dim_row` does not emit the new field.

- [ ] **Step 3: Implement the mapping**

Use the existing numeric parser and normalize zero to missing:

```python
standard_purchase_price = _num(raw.get("marketPrice"))
if standard_purchase_price == 0:
    standard_purchase_price = None
```

Write `standard_purchase_price` into the dim upsert. Keep raw `market_price` and `cbj` compatibility fields unchanged, but rename quality counters and comments to standard-purchase-price terminology.

- [ ] **Step 4: Update product quality SQL**

Use `standard_purchase_price IS NULL OR standard_purchase_price <= 0` for SKU missing-price counts. For positive inventory coverage, join `dim.v_baison_sku_standard_purchase_price` by product/color/size.

- [ ] **Step 5: Run tests**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_baison_standard_purchase_price.py tests/test_product_decision.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/baison/services/sku_service.py backend/app/api/v1/product.py backend/tests/test_baison_standard_purchase_price.py
git commit -m "feat: sync baison standard purchase price"
```

---

### Task 3: Centralize standard purchase price cost rules

**Files:**
- Create: `backend/app/core/standard_purchase_price.py`
- Delete: `backend/app/core/cost_policy.py`
- Modify: `backend/app/integrations/baison/services/pos_sale_goods_service.py`
- Modify: `backend/app/services/business_overview_service.py`
- Test: `backend/tests/test_standard_purchase_price_policy.py`
- Delete: `backend/tests/test_cost_policy.py`

**Interfaces:**
- Produces: `effective_sales_standard_cost(supplier_code, standard_purchase_price, sales_amount, sales_qty) -> Decimal | None`.
- Produces: `effective_sales_standard_cost_sql(supplier_expr, price_expr, sales_amount_expr, sales_qty_expr) -> str`.
- Missing price returns `None`; it never silently returns zero.

- [ ] **Step 1: Write failing policy tests**

```python
def test_regular_sale_uses_standard_purchase_price():
    assert effective_sales_standard_cost("G1", 80, 399, 2) == Decimal("160")

def test_missing_standard_purchase_price_stays_missing():
    assert effective_sales_standard_cost("G1", None, 399, 2) is None

def test_wenzhou_one_yuan_rule_uses_sixty_percent_of_sales():
    assert effective_sales_standard_cost("GY1229", 1, 500, 2) == Decimal("300")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_policy.py`

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement the shared policy**

Implement a Decimal-safe function and equivalent SQL. The regular SQL branch must return `NULL` for a missing price:

```sql
CASE
  WHEN supplier = 'GY1229' AND price = 1 THEN sales_amount * 0.60
  WHEN price > 0 THEN sales_qty * price
  ELSE NULL
END
```

- [ ] **Step 4: Migrate current consumers to the new helper**

Replace imports and variable names in `pos_sale_goods_service.py` and `business_overview_service.py`. Join `dim.v_baison_sku_standard_purchase_price` by product code and parsed color/size from POS `sku_code`; never use `dim_product.cost_price` as fallback.

- [ ] **Step 5: Run policy and sales rebuild tests**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_policy.py tests/test_pos_sale_goods_cost_rebuild.py`

Expected: PASS and SQL assertions reference `standard_purchase_price`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core backend/app/integrations/baison/services/pos_sale_goods_service.py backend/app/services/business_overview_service.py backend/tests/test_standard_purchase_price_policy.py backend/tests/test_pos_sale_goods_cost_rebuild.py
git rm backend/tests/test_cost_policy.py
git commit -m "refactor: centralize standard purchase price policy"
```

---

### Task 4: Unify inventory valuation and product decision consumers

**Files:**
- Modify: `backend/app/api/v1/product.py`
- Modify: `backend/app/services/inventory_analysis_service.py`
- Modify: `backend/app/services/business_overview_service.py`
- Modify: `backend/app/services/command_center_service.py`
- Modify: `backend/app/services/size_wall_service.py`
- Modify: `backend/app/services/etl/ods_to_dwd.py`
- Modify: `backend/app/services/etl/dwd_to_dws.py`
- Test: `backend/tests/test_standard_purchase_price_inventory.py`
- Modify: `backend/tests/test_apparel_inventory_consumers.py`
- Modify: `backend/tests/test_inventory_daily_cost.py`

**Interfaces:**
- Consumes: canonical view and field from Tasks 1-2.
- Produces: inventory amounts sourced only from `baison_sku.marketPrice`.
- Produces: `standard_purchase_price_coverage_rate`, `missing_standard_purchase_price_sku_count`, and `missing_standard_purchase_price_qty` in inventory/product quality payloads.

- [ ] **Step 1: Write failing inventory consistency tests**

Create fixtures with one priced SKU and one missing-price SKU. Assert:

```python
assert summary["inventory_amount"] == 5 * 80
assert summary["missing_standard_purchase_price_qty"] == 2
assert summary["missing_standard_purchase_price_sku_count"] == 1
assert summary["standard_purchase_price_coverage_rate"] == pytest.approx(5 / 7)
```

Assert `6AN10` is priced at 80 in product, inventory, size-wall, and command-center SQL paths.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
/srv/huabang-ai-center/backend/.venv/bin/pytest -q \
  tests/test_standard_purchase_price_inventory.py \
  tests/test_apparel_inventory_consumers.py \
  tests/test_inventory_daily_cost.py
```

Expected: FAIL because current consumers still use `cost_price` or independent fallback chains.

- [ ] **Step 3: Replace inventory joins**

For every positive inventory line, join the canonical view by product/color/size and calculate:

```sql
SUM(GREATEST(i.qty, 0) * sp.standard_purchase_price)
  FILTER (WHERE sp.standard_purchase_price IS NOT NULL)
```

Compute missing quantity and coverage separately; do not use `COALESCE(price, 0)` to declare completeness.

- [ ] **Step 4: Update legacy DWD inventory ETL**

Populate legacy `cost_amount` from canonical standard purchase price for compatibility, set `is_cost_missing` from the standard price, and expose the source in data-quality metadata. Do not copy old `cost_price` into the new standard field.

- [ ] **Step 5: Run focused inventory tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/product.py backend/app/services/inventory_analysis_service.py backend/app/services/business_overview_service.py backend/app/services/command_center_service.py backend/app/services/size_wall_service.py backend/app/services/etl/ods_to_dwd.py backend/app/services/etl/dwd_to_dws.py backend/tests/test_standard_purchase_price_inventory.py backend/tests/test_apparel_inventory_consumers.py backend/tests/test_inventory_daily_cost.py
git commit -m "feat: value inventory by standard purchase price"
```

---

### Task 5: Recompute sales margin and estimated operating profit

**Files:**
- Modify: `backend/app/integrations/baison/services/pos_sale_goods_service.py`
- Modify: `backend/app/services/etl/dwd_to_dws.py`
- Modify: `backend/app/services/etl/dws_to_dm.py`
- Modify: `backend/app/services/profit_service.py`
- Modify: `backend/app/services/command_center_service.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/api/v1/finance.py`
- Test: `backend/tests/test_standard_purchase_price_profit.py`
- Modify: `backend/tests/test_profit_service.py`
- Modify: `backend/tests/test_phase2_acceptance.py`
- Modify: `backend/tests/test_phase3_acceptance.py`

**Interfaces:**
- Produces: gross profit and margin based only on standard purchase price.
- Produces: estimated operating profit `gross_profit - known_expense` whenever gross profit exists.
- Status is `ready` only for complete standard purchase price coverage plus complete approved expenses; otherwise `estimated` or `pending_data` when gross profit is unavailable.

- [ ] **Step 1: Write failing profit tests**

```python
def test_missing_expense_still_returns_estimated_operating_profit():
    result = calculate_profit(..., net_sales=1000, cost_of_goods=400,
                              is_cost_complete=True, expenses=[])
    assert result.operating_profit == Decimal("600")
    assert result.operating_profit_status == "estimated"
    assert result.missing_expense_types == REQUIRED_EXPENSE_TYPES

def test_missing_standard_price_keeps_profit_estimated():
    assert snapshot["metrics"]["gross_profit"]["status"] == "estimated"
    assert snapshot["metrics"]["operating_profit"]["status"] == "estimated"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
/srv/huabang-ai-center/backend/.venv/bin/pytest -q \
  tests/test_standard_purchase_price_profit.py \
  tests/test_profit_service.py \
  tests/test_phase2_acceptance.py \
  tests/test_phase3_acceptance.py
```

Expected: FAIL because incomplete expenses currently hide operating profit.

- [ ] **Step 3: Update deterministic profit calculation**

Set `operating_profit = gross_profit - total_expense` whenever gross profit is present. Use:

```python
if gross_profit is None:
    operating_profit_status = "pending_data"
elif not reasons:
    operating_profit_status = "ready"
else:
    operating_profit_status = "estimated"
```

Calculate operating margin only for positive net sales. Keep all reasons and missing expense types.

- [ ] **Step 4: Persist and expose the estimated value**

Update DWS/DM, command-center snapshot, report, and finance payloads so `operating_profit` is not set back to `None` when status is `estimated`. Include known expense amount, coverage rate, and a human-readable missing list in the metric reason.

- [ ] **Step 5: Preserve AI/rule guardrails**

Keep `_can_assert_operating_profit` and profit rules restricted to `ready` plus finance-approved data. Update tests to prove an estimated negative value is displayed but never becomes a definitive loss conclusion.

- [ ] **Step 6: Run focused tests**

Run the command from Step 2 plus:

```bash
/srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_ai_command_center_guardrails.py tests/test_profit_exception_rules.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/baison/services/pos_sale_goods_service.py backend/app/services/etl backend/app/services/profit_service.py backend/app/services/command_center_service.py backend/app/services/report_service.py backend/app/api/v1/finance.py backend/tests
git commit -m "feat: calculate profit from standard purchase price"
```

---

### Task 6: Unify AI diagnosis and rule evidence

**Files:**
- Modify: `backend/app/services/ai_diagnosis_service.py`
- Modify: `backend/app/services/ai_engine.py`
- Modify: `backend/app/services/rule_engine.py`
- Test: `backend/tests/test_standard_purchase_price_ai.py`
- Modify: `backend/tests/test_ai_diagnosis_inventory.py`
- Modify: `backend/tests/test_ai_command_center_guardrails.py`

**Interfaces:**
- Consumes: canonical standard purchase price data and completeness status.
- Produces: AI evidence with `standard_purchase_price`, `source=baison_sku.marketPrice`, and coverage.
- Definitive profit rules still require `ready` and approved finance.

- [ ] **Step 1: Write failing AI consistency tests**

Assert no AI SQL contains `sku.cost_price`, `sku.market_price`, or `product.cost_price` fallback chains. Assert evidence for `6AN10` uses 80 and evidence with a missing price contains `缺标准进价`.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_ai.py tests/test_ai_diagnosis_inventory.py tests/test_ai_command_center_guardrails.py`

Expected: FAIL on current fallback SQL and terminology.

- [ ] **Step 3: Replace AI and rule data sources**

Join the canonical view and use the persisted DWS amounts. Add source and coverage to evidence. Keep missing values as null and append an explicit limitation instead of substituting zero.

- [ ] **Step 4: Update sensitive-query terminology**

Keep the existing `cost` permission capability but recognize “标准进价” in prompts and user questions. System prompts must call the field “标准进价”.

- [ ] **Step 5: Run tests**

Run the command from Step 2 plus `tests/test_profit_exception_rules.py`.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai_diagnosis_service.py backend/app/services/ai_engine.py backend/app/services/rule_engine.py backend/tests/test_standard_purchase_price_ai.py backend/tests/test_ai_diagnosis_inventory.py backend/tests/test_ai_command_center_guardrails.py
git commit -m "feat: align ai diagnosis to standard purchase price"
```

---

### Task 7: Expose authorized standard purchase price in the frontend

**Files:**
- Modify: `backend/app/api/v1/product.py`
- Modify: `backend/app/core/field_permissions.py`
- Modify: `frontend/src/api/product.ts`
- Modify: `frontend/src/views/product/SkuArchive.vue`
- Modify: `frontend/src/views/product/ProductMaster.vue`
- Modify: `frontend/src/views/product/Index.vue`
- Modify: `frontend/src/views/inventory/InventoryBalance.vue`
- Modify: `frontend/src/views/dashboard/Index.vue`
- Modify: `frontend/src/views/report/Index.vue`
- Modify: `frontend/src/views/finance/Index.vue`
- Test: `backend/tests/test_standard_purchase_price_permissions.py`
- Test: `frontend/tests/standard-purchase-price.test.cjs`

**Interfaces:**
- Produces: SKU list query parameter `standard_purchase_price_status=missing|ready`.
- Produces: authorized response field `standard_purchase_price`; unauthorized response omits or nulls it.
- Produces: visible labels “标准进价” and “缺标准进价”.

- [ ] **Step 1: Write failing permission/API/frontend tests**

Backend assertions:

```python
assert admin_item["standard_purchase_price"] == 80
assert normal_item["standard_purchase_price"] is None
assert missing_filter_sql_uses_standard_purchase_price
```

Frontend source-contract assertions:

```javascript
assert.match(skuArchiveSource, /标准进价/)
assert.match(skuArchiveSource, /缺标准进价/)
assert.doesNotMatch(skuArchiveSource, /缺成本/)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_permissions.py
cd ../frontend && node --test tests/standard-purchase-price.test.cjs
```

Expected: FAIL because the field, filter, and labels do not exist.

- [ ] **Step 3: Implement field-level permission output**

Return standard price only after applying the product field rule. Admin remains unrestricted; copied legacy permissions preserve current role behavior. The API must not return old `cost_price`.

- [ ] **Step 4: Add the SKU column and missing-price filter**

Add an Element Plus select with `全部 / 已维护 / 缺标准进价`, and an authorized numeric column formatted to two decimals. Preserve existing inventory and sales sorting.

- [ ] **Step 5: Replace user-visible terminology**

Across the listed pages, replace price labels and missing-price status with “标准进价”. Keep “销售成本金额” only where it denotes an aggregate amount, and add source notes where space permits.

- [ ] **Step 6: Run frontend and permission tests**

Run:

```bash
cd backend && /srv/huabang-ai-center/backend/.venv/bin/pytest -q tests/test_standard_purchase_price_permissions.py
cd ../frontend && node --test tests/standard-purchase-price.test.cjs && npm run type-check && npm run build
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/product.py backend/app/core/field_permissions.py backend/tests/test_standard_purchase_price_permissions.py frontend/src
git commit -m "feat: show authorized standard purchase price"
```

---

### Task 8: Rebuild, compare, verify, and deploy

**Files:**
- Create: `backend/scripts/rebuild_standard_purchase_price_metrics.py`
- Create: `docs/acceptance/standard-purchase-price-unification.md`
- Modify: `docs/superpowers/plans/2026-07-15-standard-purchase-price-unification.md`

**Interfaces:**
- Produces: idempotent rebuild command accepting `--start-date`, `--end-date`, and `--inventory-date`.
- Produces: before/after comparison for inventory amount, sales cost, gross profit, gross margin, operating profit, and price coverage.

- [ ] **Step 1: Write the rebuild script dry-run test**

Create a test that runs `main(..., dry_run=True)` twice and asserts identical SQL targets and no Baison integration method calls.

- [ ] **Step 2: Implement the idempotent rebuild**

The script must run SKU backfill, DWS sales/inventory rebuild, DM finance/report rebuild, command-center snapshot rebuild, warnings, and diagnosis in one transaction per business date. `--dry-run` prints counts and differences without writing.

- [ ] **Step 3: Run full automated verification**

Run:

```bash
cd backend
/srv/huabang-ai-center/backend/.venv/bin/pytest -q
/srv/huabang-ai-center/backend/.venv/bin/alembic upgrade head
cd ../frontend
node --test tests/*.test.cjs
npm run type-check
npm run build
```

Expected: all tests pass, Alembic exits 0, and production assets build.

- [ ] **Step 4: Run dry-run and review the comparison**

Run:

```bash
cd backend
/srv/huabang-ai-center/backend/.venv/bin/python scripts/rebuild_standard_purchase_price_metrics.py \
  --start-date 2026-06-15 --end-date 2026-07-14 --inventory-date 2026-07-15 --dry-run
```

Expected: SKU coverage about 99.47%, positive-inventory quantity coverage 100%, sales quantity coverage about 99.94%, and no Baison API calls.

- [ ] **Step 5: Run the real rebuild and production smoke tests**

After merging, run the same command without `--dry-run`, restart `huabang-backend.service`, and verify `/health`, `/api/v1/dashboard/overview?stat_date=2026-07-14`, product SKU, inventory, report, finance, diagnosis, and mobile endpoints.

- [ ] **Step 6: Run Playwright desktop/mobile checks**

Capture `/app/dashboard`, `/app/report`, `/app/product`, `/app/product/skus`, `/app/inventory`, `/app/finance`, and `/app/ai-diagnosis` at desktop and mobile widths. Verify no old “成本价/缺成本” labels, no text overlap, and standard-price amounts are permission-protected.

- [ ] **Step 7: Record acceptance evidence and commit**

Document exact before/after numbers, test totals, migration round trip, endpoint responses, screenshots, and rollback command.

```bash
git add backend/scripts/rebuild_standard_purchase_price_metrics.py docs/acceptance/standard-purchase-price-unification.md docs/superpowers/plans/2026-07-15-standard-purchase-price-unification.md
git commit -m "docs: record standard purchase price acceptance"
```
