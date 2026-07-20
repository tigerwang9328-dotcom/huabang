# Progress

## 2026-07-20

- Confirmed full writable finance-center scope and independent Huabang ledger architecture.
- Committed design as `1e8aa7d`.
- Reviewed and committed implementation plan as `f074224`.
- Started isolated-workspace and baseline verification.
- CodeGraph marker exists but the index is unavailable; continued with ordinary source inspection as instructed.
- Initial parallel config probe included absent optional files and returned exit 1; no files or services were changed.
- Baseline Alembic probe found no standalone executable on PATH; switched to the module entry point.
- Full pytest reached collection but was blocked before tests by missing required settings; production secrets were not copied into the worktree.
- Frontend baseline passed `npm run type-check` and `npm run build`.
- Python 3.14 could not install the locked PostgreSQL binary dependency; searching for a compatible project runtime.
- Created a Python 3.12 project venv and installed locked requirements successfully.
- Confirmed current Alembic head `2d1f6a7b8c96`.
- Backend baseline completed with 613 passing and 36 pre-feature environment/data failures.
- Began Task 1 model-contract TDD.
- Task 1 model tests moved from expected import failure to 7 passing tests; combined finance tests are 24 passing.
- New Alembic revision is the sole head `3e1f6a7b8c97`; database execution validation is next.
- Added writable `fin` core and operational model contracts for books, periods, accounts, vouchers, voucher entries, ledger balances, statement mappings, receivables, payables, cash, bank transactions, fixed assets, invoices, payroll, tax records, and auto-entry runs.
- Fixed review blockers in Task 1: nullable manual lineage with partial unique indexes, composite book-scoped foreign keys, canonical ledger uniqueness, versioned statement templates, operational amount checks, FK indexes, deferred voucher validation trigger, posted-entry immutability trigger, migration-owned permission seeding, finance/boss role grants, and grant-safe downgrade backup.
- Verified isolated PostgreSQL 16 upgrade path by creating current non-`fin` schema, stamping `2d1f6a7b8c96`, and upgrading to `3e1f6a7b8c97`; result was one Alembic head, 26 `fin` tables, and 7 `finance_center` permissions.
- Verified database behavior: cross-book voucher periods fail, manual receivables with null `source_pk` coexist, duplicate imported source rows fail, non-draft vouchers need entries and balanced totals, reviewed voucher entries are immutable, closed-period manual review fails after entry validation, and staged `kingdee_history` vouchers can post in closed periods.
- Verified downgrade and pre-existing permission safety: `finance:center:view` with legacy metadata survived upgrade/downgrade, migration-added grants were removed on downgrade, and `fin` tables dropped without downgrade `CASCADE`.
- Current focused checks: `test_finance_center_models.py` plus `test_kingdee_finance_models.py` passed 14 tests; `test_task_workflow.py` passed 21 tests from backend cwd; `alembic current` and `alembic heads` both report `3e1f6a7b8c97`.
- Independent reviews found additional Task 1 blockers: non-book-scoped account/voucher self references, core lineage duplicate source risk, tax record source-key mismatch, free-form settlement targets, draft-voucher references to non-draft vouchers, static/config tables carrying draft voucher links, statement mappings not version-isolated, and entry updates that could move rows away from reviewed vouchers.
- Fixed those review blockers with composite self-FKs, core partial unique source indexes, tax source partial unique index plus period key, typed settlement receivable/payable FKs with exactly-one target check, draft-voucher guard triggers, split operation mixins, statement mapping uniqueness by statement line, and OLD/NEW voucher-entry immutability checks.
- Re-verified isolated PostgreSQL 16 upgrade/downgrade after review fixes; upgrade reached head `3e1f6a7b8c97`, downgrade removed `fin` tables and `app.finance_center_permission_grant_backup`, and re-upgrade restored 26 `fin` tables.
- Added manual database behavior evidence after review fixes: duplicate core imported source rows fail, cross-book account parent and voucher reversal fail, moving a reviewed voucher entry to a draft voucher fails, operation records cannot attach to reviewed vouchers, settlement requires exactly one typed target, cross-book settlement targets fail, and valid typed settlement targets succeed.
