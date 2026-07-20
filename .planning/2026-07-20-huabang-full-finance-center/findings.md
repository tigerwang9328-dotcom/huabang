# Findings

- Production historical finance currently contains three verified books, 339 vouchers, 4,596 entries, 416 accounts, and 6,868 monthly balances.
- Existing Kingdee ODS/DWD records are the immutable evidence layer; the new formal ledger must reference them through source links.
- Mumaren is a behavior and interaction reference only. Its specialized business data, templates, and local production patches are not copied.
- The implementation plan is `docs/superpowers/plans/2026-07-20-huabang-full-finance-center.md`.
- Baseline Alembic head is `2d1f6a7b8c96`.
- Frontend baseline type-check and production build pass.
- Backend baseline under Python 3.12: 613 passed and 36 failed. Failures are pre-feature and cluster around missing `greenlet`, unavailable local PostgreSQL business data, and Windows locale reads of UTF-8 source.
- The pre-existing Alembic chain is not blank-database bootstrappable: revision `d2e3f4a5b6c7` assumes `dim.dim_store` already exists. Production-style upgrades must start from the current schema/head rather than an empty database.
- The writable `fin` ledger must enforce book isolation in the database, not just in services. Task 1 now uses composite `(book_id, id)` parent keys and composite child FKs for periods, accounts, auxiliary items, vouchers, and operational draft references.
- Non-draft voucher validity cannot rely on application code only. Task 1 now uses a deferred PostgreSQL constraint trigger to reject non-draft vouchers without entries, unbalanced headers, header/entry total mismatches, missing periods, and non-Kingdee posting/review in closed periods.
- Posted/reviewed/reversed voucher entries must be immutable at the row level. Task 1 now rejects insert/update/delete on entries once the owning voucher is not `draft`.
- Manual records need nullable source keys. Imported source rows are protected by partial unique source indexes where `source_pk IS NOT NULL`, avoiding the earlier single-manual-row trap.
- Permission migrations need two safety layers: permission rows created by this migration are marked with `migration:3e1f6a7b8c97`, and role grants added by this migration are backed up in `app.finance_center_permission_grant_backup` so downgrade removes only migration-added grants.
- Account parentage and voucher reversal links are financial references and must be book-scoped just like voucher entries. Task 1 now enforces `(book_id, parent_id)` and `(book_id, reversal_of_id/reversed_by_id)` composite FKs.
- Polymorphic settlement `target_type/target_id` was too weak for accounting. Task 1 now uses typed nullable `receivable_id` / `payable_id` composite FKs with an exactly-one target check.
- Operational `draft_voucher_id` is a transaction-only link. Static/config records such as cash accounts and auto-entry rules do not carry it; transaction records are guarded by a PostgreSQL trigger requiring the referenced voucher to still be `draft`.
- Statement mappings must survive report-template versioning. Task 1 now keys mappings by `statement_line_id`, allowing mappings for different template versions to coexist.
