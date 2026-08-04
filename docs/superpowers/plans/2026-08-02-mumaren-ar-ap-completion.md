# Mumaren AR/AP Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the independent Huabang receivable/payable ledgers and ageing analysis to the safe functional level of the extracted Mumaren UI.

**Architecture:** Keep the independent `finance_center_mumaren` schema and the existing state machine: draft -> finance review -> manual settlement. Add an order-level contact snapshot and an atomic draft-line replacement path; render these through the existing three AR/AP routes and the shared book selection.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic/PostgreSQL, Vue 3, Element Plus, Node test runner, pytest.

## Global Constraints

- Never call legacy finance APIs or tables.
- Kingdee-migrated books remain permanently read-only at UI, API, and database layers.
- AR/AP does not auto-generate vouchers or auto-settle.
- An order can only be changed while draft; non-empty replacement lines must exactly equal its total amount. An empty replacement list deliberately represents a header-only order and clears existing detail lines.

### Task 1: Persist order contacts and safe draft-line replacement

**Files:**
- Modify: `backend/app/models/mumaren_finance_center_domains.py`
- Modify: `backend/app/services/mumaren_finance_center/ar_ap.py`
- Modify: `backend/app/api/v1/mumaren_finance_center_domains.py`
- Create: `backend/alembic/versions/<revision>_complete_mumaren_ar_ap_orders.py`
- Test: `backend/tests/test_mumaren_finance_center_ar_ap_details.py`

- [ ] Write tests proving a draft update preserves a contact snapshot, replaces all details atomically, rejects mismatched total, and rejects historical or reviewed records.
- [ ] Run the new tests and confirm each fails because the API/model does not support the contract.
- [ ] Add `contact` to both independent AR/AP order tables, include it in API data, and replace lines only after validating all line amounts equal the requested total.
- [ ] Create one forward-only Alembic revision from the current single head. Add nullable columns only; do not alter Kingdee data or legacy schemas.
- [ ] Run the focused pytest suite and `alembic heads`; expected: tests pass and exactly one head.

### Task 2: Complete the three AR/AP user flows

**Files:**
- Modify: `frontend/src/api/mumarenFinanceCenter.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceArAp.vue`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceArApAging.vue`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] Write static/contract tests for contact input and display, editable draft lines, ageing drilldown, shared-book reload, and read-only historical controls.
- [ ] Run the frontend test and confirm the contract fails before changing production code.
- [ ] Extend API types and payloads, preserve all details in the edit form, and render the contact in the ledger/detail drawer.
- [ ] Make ageing rows expandable by counterparty to show their source documents; keep CSV export scoped to the currently selected book and cutoff.
- [ ] Run `node --test tests/mumaren-finance-center.test.cjs`, `npm run type-check`, and `npm run build`.

### Task 3: Release evidence

**Files:**
- Modify only the Task 1/2 files and their tests.

- [ ] Run focused backend tests plus migration-head validation and frontend build.
- [ ] Obtain independent code review; resolve every P0/P1 before committing.
- [ ] Commit only the reviewed AR/AP files, back up exact production targets, apply the migration, deploy the built frontend and backend source, restart the backend, and verify health.
- [ ] Run browser acceptance while logged in: current book creates a draft with contact and lines, reviews it, registers a manual settlement, and shows it in ageing; a Kingdee book refuses every write control.
