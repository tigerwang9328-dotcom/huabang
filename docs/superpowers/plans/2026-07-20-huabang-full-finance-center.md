# Huabang Full Finance Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete writable finance center in Huabang, migrate the three verified Kingdee account sets into a formal double-entry ledger, and preserve immutable source evidence.

**Architecture:** Keep `ods.kingdee_*` and `dwd.dwd_gl_*` immutable. Add a transactional `fin` schema for writable accounting and operational modules, with source links and versioned audit. Business sources generate drafts only; posted vouchers alone update ledgers and legal statements.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, Pydantic, Vue 3, TypeScript, Pinia, Element Plus, pytest, Playwright.

## Global Constraints

- Never update or delete Kingdee ODS/DWD source rows.
- Never write back to the Kingdee server.
- Preserve three independent legal-entity books.
- Imported history starts posted; covered periods start closed.
- Posted vouchers require unpost before edit; closed periods require unclose before unpost.
- Auto-entry creates drafts only and never reviews or posts automatically.
- Legal statements remain non-ready while active accounts are unmapped or periods have gaps.
- Do not overwrite `dwd_finance_expense`, `dwd_finance_cash`, Baison facts, or DingTalk facts.
- Every write stores actor, reason, version, source links, and timestamps.
- Production changes require a fresh full backup and a single Alembic head.

---

### Task 1: Finance Domain Models And Migration

**Files:**
- Create: `backend/app/models/finance_core.py`
- Create: `backend/app/models/finance_operations.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/3e1f6a7b8c97_full_finance_center.py`
- Test: `backend/tests/test_finance_center_models.py`

**Interfaces:**
- Produces: `FinBook`, `FinPeriod`, `FinAccount`, `FinAuxCategory`, `FinAuxItem`, `FinVoucher`, `FinVoucherEntry`, `FinVoucherVersion`, `FinLedgerBalance`, `FinStatementLine`, `FinStatementMapping`, `FinOperationLog`, `FinSourceLink`.
- Produces: operational models for receivables, payables, settlements, cash accounts, bank transactions, reconciliations, fixed assets, depreciation, invoices, payroll, tax, auto-entry rules and runs.

- [ ] Write model-contract tests asserting schema names, unique keys, foreign keys, status columns, source lineage, numeric precision and version columns.
- [ ] Run `pytest tests/test_finance_center_models.py -q`; expect failures because models do not exist.
- [ ] Implement focused model files. Use `Numeric(18, 4)` for accounting amounts and unique keys `(book_id, voucher_no)`, `(book_id, account_code)`, `(book_id, period)`, `(book_id, account_id, period)` and `(book_id, source_system, source_database, source_pk)` where applicable.
- [ ] Add migration `down_revision = "2d1f6a7b8c96"`; create schema `fin`, all tables, indexes, constraints and permission seed rows in one transactional revision.
- [ ] Register models and run `python -m pytest tests/test_finance_center_models.py -q`; expect PASS.
- [ ] Run `alembic heads`; expect exactly `3e1f6a7b8c97 (head)`.
- [ ] Commit with `git commit -m "feat: add writable finance domain schema"`.

### Task 2: Voucher State Machine And Ledger Engine

**Files:**
- Create: `backend/app/services/finance_center/errors.py`
- Create: `backend/app/services/finance_center/voucher_service.py`
- Create: `backend/app/services/finance_center/ledger_service.py`
- Create: `backend/app/services/finance_center/period_service.py`
- Test: `backend/tests/test_finance_voucher_state_machine.py`
- Test: `backend/tests/test_finance_ledger_engine.py`

**Interfaces:**
- Produces: `VoucherService.create_draft()`, `update_draft()`, `review()`, `post()`, `unpost()`, `reverse()`, `delete_draft()`.
- Produces: `PeriodService.close()`, `unclose()`, `assert_open()`.
- Produces: `LedgerService.rebuild_period()` and `trial_balance()`.

- [ ] Write failing tests for balanced/unbalanced drafts, optimistic version conflicts, closed-period rejection, post/unpost idempotency, reversal linkage and version snapshots.
- [ ] Run both test files; expect import failures.
- [ ] Implement domain errors with stable codes: `FIN_PERIOD_CLOSED`, `FIN_UNBALANCED`, `FIN_INVALID_STATE`, `FIN_VERSION_CONFLICT`, `FIN_MAPPING_REQUIRED`, `FIN_DUPLICATE_SOURCE`.
- [ ] Implement state transitions in database transactions. Lock `FinPeriod` with `SELECT FOR UPDATE`; never mutate ledger outside post/unpost/rebuild.
- [ ] Compute ledger balances from posted entries only. Validate `opening + debit - credit = closing` using balance direction and Decimal arithmetic.
- [ ] Write operation logs and full before/after voucher versions for every mutation.
- [ ] Run tests; expect PASS and zero floating-point use.
- [ ] Commit with `git commit -m "feat: add voucher lifecycle and ledger engine"`.

### Task 3: Verified Kingdee History Migration

**Files:**
- Create: `backend/scripts/migrate_kingdee_to_finance.py`
- Create: `backend/app/services/finance_center/history_migration.py`
- Test: `backend/tests/test_finance_history_migration.py`

**Interfaces:**
- Consumes: existing `DimLegalEntity`, `DimFinanceAccount`, `DwdGlVoucher`, `DwdGlVoucherEntry`, `DwdGlBalanceMonthly`.
- Produces: `HistoryMigrationService.validate()`, `apply()`, `snapshot()` and `compare()`.

- [ ] Write failing tests using the verified per-book baselines: `77/871/150/1378`, `244/3476/219/4940`, `18/249/47/550`.
- [ ] Add assertions for global totals `339/4596/416/6868`, debit and credit `38606208.6600`, source-link completeness and repeated-run stability.
- [ ] Implement book, period, account, auxiliary item, voucher, entry and balance migration with upserts keyed by source lineage.
- [ ] Import vouchers as `posted`, preserve `source_status`, set `origin_kind="kingdee_history"`, and close all covered periods.
- [ ] Create `pending_gap` quality issues from each book's last Kingdee period through the chosen continuous takeover period.
- [ ] Run validate-only against production-shaped test data; expect zero errors before `--apply` is permitted.
- [ ] Run apply twice in a test database and compare snapshots byte-for-byte.
- [ ] Commit with `git commit -m "feat: migrate verified Kingdee history into formal ledger"`.

### Task 4: Statement Mapping And Legal Reports

**Files:**
- Create: `backend/app/services/finance_center/statement_mapping.py`
- Create: `backend/app/services/finance_center/report_service.py`
- Create: `backend/app/api/v1/finance_center/reports.py`
- Test: `backend/tests/test_finance_statement_mapping.py`
- Test: `backend/tests/test_finance_reports_api.py`

**Interfaces:**
- Produces: `suggest_mappings(book_id)`, `confirm_mapping(mapping_id, actor)`, `statement_status(book_id, period, type)`.
- Produces read models for trial balance, general ledger, subsidiary ledger, balance sheet, profit statement and cash flow statement.

- [ ] Write failing tests that map account code prefixes to Chinese accounting statement lines while leaving unknown active accounts `suggested`.
- [ ] Test report states `pending_mapping`, `pending_data`, `pending_gap`, `ready` and forbid official export unless ready.
- [ ] Implement versioned statement templates for enterprise and small-enterprise standards.
- [ ] Implement current-period and year-to-date calculations from posted ledger entries.
- [ ] Add drilldown payloads from statement line to accounts, entries, vouchers and source links.
- [ ] Run report tests and compare statement totals to trial balance.
- [ ] Commit with `git commit -m "feat: add mapped legal statements and ledger reports"`.

### Task 5: Receivables, Payables, Cash And Reconciliation

**Files:**
- Create: `backend/app/services/finance_center/receivable_service.py`
- Create: `backend/app/services/finance_center/payable_service.py`
- Create: `backend/app/services/finance_center/cash_service.py`
- Create: `backend/app/api/v1/finance_center/operations.py`
- Test: `backend/tests/test_finance_receivable_payable.py`
- Test: `backend/tests/test_finance_cash_reconciliation.py`

**Interfaces:**
- Produces open-item APIs, settlements, aging buckets, cash accounts, statement imports and reconciliation results.
- Calls `VoucherService.create_draft()` only; never posts automatically.

- [ ] Write failing tests for partial settlement, over-settlement rejection, reversal, aging dates, statement duplicate detection and reconciliation differences.
- [ ] Implement receivable/payable lifecycles `open/partial/settled/cancelled` with source documents and counterparty auxiliaries.
- [ ] Implement cash accounts and bank transactions with statement hashes and reconciliation links.
- [ ] Generate draft receipts/payments and preserve the source chain.
- [ ] Run tests; assert ledger counts stay unchanged until manual review/post.
- [ ] Commit with `git commit -m "feat: add receivables payables and treasury operations"`.

### Task 6: Assets, Invoices, Payroll And Tax

**Files:**
- Create: `backend/app/services/finance_center/asset_service.py`
- Create: `backend/app/services/finance_center/invoice_service.py`
- Create: `backend/app/services/finance_center/payroll_service.py`
- Create: `backend/app/services/finance_center/tax_service.py`
- Create: `backend/app/api/v1/finance_center/specialized.py`
- Test: `backend/tests/test_finance_specialized_modules.py`

**Interfaces:**
- Produces fixed-asset cards and depreciation schedules, invoice registers, payroll batches and tax ledgers.
- Calls `VoucherService.create_draft()` with deterministic source keys.

- [ ] Write failing tests for straight-line depreciation, disposal, invoice amount/tax validation, payroll totals and tax paid/unpaid calculations.
- [ ] Implement Decimal-based schedules and source-linked draft generation.
- [ ] Ensure salary and tax fields require sensitive finance permissions.
- [ ] Ensure reruns return the existing valid draft or explicitly void and replace it; never duplicate.
- [ ] Run tests; expect PASS.
- [ ] Commit with `git commit -m "feat: add assets invoices payroll and tax modules"`.

### Task 7: Auto-Entry Rules And Source Adapters

**Files:**
- Create: `backend/app/services/finance_center/auto_entry_service.py`
- Create: `backend/app/services/finance_center/adapters/baison.py`
- Create: `backend/app/services/finance_center/adapters/dingtalk.py`
- Create: `backend/app/api/v1/finance_center/auto_entry.py`
- Test: `backend/tests/test_finance_auto_entry.py`

**Interfaces:**
- Produces `preview_run()`, `execute_run()`, `list_exceptions()`.
- Adapters emit a common `SourceDocument` containing source identity, book, date, amount, tax, counterparty, organization and attachments.

- [ ] Write failing tests for sales, return, purchase receipt, reimbursement, payment and payroll mappings.
- [ ] Test that missing account/org/counterparty mappings create explicit exception records.
- [ ] Implement rule precedence by book, business type and effective period.
- [ ] Generate balanced drafts only; include source links and attachments.
- [ ] Verify no adapter invokes review or post.
- [ ] Commit with `git commit -m "feat: add finance draft automation adapters"`.

### Task 8: Finance API, Permissions And Audit

**Files:**
- Create: `backend/app/api/v1/finance_center/__init__.py`
- Create: `backend/app/api/v1/finance_center/books.py`
- Create: `backend/app/api/v1/finance_center/vouchers.py`
- Create: `backend/app/api/v1/finance_center/ledgers.py`
- Create: `backend/app/api/v1/finance_center/settings.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_finance_center_api.py`
- Test: `backend/tests/test_finance_center_permissions.py`

**Interfaces:**
- Exposes `/api/v1/finance-center/*` and keeps `/api/v1/finance/*` existing endpoints stable.

- [ ] Write API tests for all state-changing commands with version and reason requirements.
- [ ] Seed permissions `finance:center:view`, `finance:voucher:write`, `finance:voucher:post`, `finance:period:close`, `finance:settings:write`, `finance:sensitive:view`, `finance:export`.
- [ ] Grant all finance permissions to finance roles, read/export to boss roles and none by default.
- [ ] Implement routers and consistent pagination/filter contracts.
- [ ] Return business `code=409` for version/state conflicts and `code=403` for permission rejection under the project's existing response convention.
- [ ] Run API and permission tests.
- [ ] Commit with `git commit -m "feat: expose secured finance center APIs"`.

### Task 9: Complete Finance Center Frontend

**Files:**
- Create: `frontend/src/api/financeCenter.ts`
- Create: `frontend/src/stores/financeCenter.ts`
- Create: `frontend/src/views/finance-center/FinanceLayout.vue`
- Create: `frontend/src/views/finance-center/FinanceDashboard.vue`
- Create: `frontend/src/views/finance-center/VoucherWorkspace.vue`
- Create: `frontend/src/views/finance-center/LedgerWorkspace.vue`
- Create: `frontend/src/views/finance-center/StatementWorkspace.vue`
- Create: `frontend/src/views/finance-center/ReceivablePayable.vue`
- Create: `frontend/src/views/finance-center/TreasuryWorkspace.vue`
- Create: `frontend/src/views/finance-center/SpecializedWorkspace.vue`
- Create: `frontend/src/views/finance-center/PeriodClosing.vue`
- Create: `frontend/src/views/finance-center/FinanceSettings.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `backend/tests/test_finance_center_frontend_contract.py`

**Interfaces:**
- Consumes `/api/v1/finance-center/*`.
- Preserves `/app/fin/history/*` as redirects.

- [ ] Write route/menu/API contract tests for every finance module.
- [ ] Build a shared account-set and period toolbar, stable responsive table dimensions, amount drilldown and source-snapshot drawer.
- [ ] Build voucher editing with balanced totals, version conflict handling, required reason dialogs and explicit state actions.
- [ ] Build legal statement status banners; hide official export while not ready.
- [ ] Build operational workspaces with actual create/edit/query flows and explicit empty/data-gap states.
- [ ] Use existing Element Plus icons and Huabang styling; do not copy Mumaren brand text or inline-heavy layouts.
- [ ] Run `npm run type-check` and `npm run build`; expect exit 0.
- [ ] Run Playwright at 1440x900 and 390x844 through dashboard, voucher edit, ledger drilldown, statement status and closing flows; expect no overlap or console errors.
- [ ] Commit with `git commit -m "feat: build complete finance center experience"`.

### Task 10: Full Trial Migration And Production Rollout

**Files:**
- Create: `backend/scripts/verify_finance_center.py`
- Create: `docs/finance/finance-center-runbook.md`
- Update: `D:/huabang/invest_kingdee/results/K3MIG_20260717_172928/kingdee_finance_implementation_report.md`

**Interfaces:**
- Produces machine-readable JSON verification and a human-readable reconciliation report.

- [ ] Create a fresh PostgreSQL trial database from a production schema-only dump.
- [ ] Apply Alembic and assert one head.
- [ ] Run historical migration twice and compare batches, rows, sums and source hashes.
- [ ] Execute state-machine scenarios on copied test vouchers: unclose, unpost, edit, review, post, close and reverse.
- [ ] Verify all source ODS/DWD and Baison/DingTalk facts remain unchanged.
- [ ] Run the complete backend tests, API tests, frontend type-check/build and Playwright acceptance.
- [ ] Before production, create and verify a full custom-format PostgreSQL backup and preserve the old frontend build.
- [ ] Apply migration and import in production; stop on any baseline mismatch.
- [ ] Restart only the backend process and atomically switch the frontend build.
- [ ] Re-run API, permission, browser, balance and idempotency acceptance against production.
- [ ] Create a post-release backup, append the runbook/report and retain all worktrees, restore databases and source files until explicit cleanup approval.
- [ ] Commit with `git commit -m "docs: add finance center rollout evidence"`.

## Completion Gate

- [ ] Every named module has a working API and working page, not a static placeholder.
- [ ] Historical baseline and amount checks are exact.
- [ ] Full voucher lifecycle works with audit and concurrency protection.
- [ ] Statements cannot become official without confirmed mapping and continuous periods.
- [ ] Auto-entry creates drafts only.
- [ ] Finance, boss and non-finance permission behavior is verified.
- [ ] Alembic has one head; all tests and builds pass.
- [ ] Trial and production evidence are saved, and pre/post backups are verified.
