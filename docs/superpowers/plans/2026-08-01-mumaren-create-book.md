# Mumaren Finance Book Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authorized finance user create an isolated Mumaren finance book and receive usable starter accounts plus the twelve open fiscal periods for 2026.

**Architecture:** Add one transaction-owned service function that validates book identity, flushes the new book, seeds a fixed minimal starter chart and its 2026 periods, and records the action. Expose it through the existing Mumaren finance API with the existing finance-write gate; the ledger page posts the four requested fields and sets the returned ID in the shared selected-book composable.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3 Composition API, Element Plus, pytest, Node test runner.

## Global Constraints

- Keep every new book in `finance_center_mumaren`; never read, copy, or write legacy finance tables.
- Retain draft, human review, and manual posting accounting workflow.
- Accept only unique uppercase alphanumeric, underscore, or hyphen book codes, 1-64 characters.
- Seed only a fixed starter chart and `2026-01` through `2026-12` open periods; do not clone another tenant's settings.

### Task 1: Domain creation transaction

**Files:**
- Modify: `backend/app/services/mumaren_finance_center/workflow.py`
- Test: `backend/tests/test_mumaren_finance_center_book_creation.py`

**Interfaces:**
- Produces: `create_book(db, book_code, book_name, company_name, status, operator_id) -> FinanceCenterMumarenBook`.
- Produces: `InvalidBookCreationError` for duplicate or invalid book requests.

- [ ] **Step 1: Write failing tests** for a valid creation with independent accounts, twelve `open` 2026 periods, and an audit item; and for duplicate code rejection.
- [ ] **Step 2: Run the new pytest module** and confirm it fails because `create_book` does not exist.
- [ ] **Step 3: Implement the minimal validated transaction** using `flush()` after the book insert, fixed seed rows, and `FinanceCenterMumarenAuditLog(action="create_book")`.
- [ ] **Step 4: Re-run the module** and confirm both behaviors pass.

### Task 2: Authenticated API contract

**Files:**
- Modify: `backend/app/api/v1/mumaren_finance_center.py`
- Test: `backend/tests/test_mumaren_finance_center_book_creation.py`

**Interfaces:**
- Consumes: `BookCreateInput` and workflow `create_book`.
- Produces: `POST /api/v1/finance-center/mumaren/books` returning the normal book response object.

- [ ] **Step 1: Write a failing route test** asserting that four valid inputs call the creator as the current user and return its ID, and a domain validation failure becomes HTTP 400.
- [ ] **Step 2: Run the route test** and confirm no POST route exists.
- [ ] **Step 3: Add `BookCreateInput`, response serialization, and the POST route** guarded by `require_mumaren_voucher_write`.
- [ ] **Step 4: Re-run the route test** and confirm it passes.

### Task 3: Ledger-management UI

**Files:**
- Modify: `frontend/src/api/mumarenFinanceCenter.ts`
- Modify: `frontend/src/composables/useMumarenFinanceBook.ts`
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceLedgers.vue`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

**Interfaces:**
- Adds `CreateMumarenFinanceBookPayload` and `mumarenFinanceCenterApi.createBook(payload)`.
- Adds `selectBook(bookId)` to `useMumarenFinanceBook()`.

- [ ] **Step 1: Write a failing static/component contract test** for the create API, dialog fields, submit handler, and selected-book update.
- [ ] **Step 2: Run the frontend test** and confirm it fails against the read-only page.
- [ ] **Step 3: Implement one Element Plus dialog** with code, name, company, and active/inactive fields; disable submit while saving; display API errors; refresh and select the returned book on success.
- [ ] **Step 4: Re-run the frontend test** and confirm it passes.

### Task 4: Verification and release

**Files:**
- No functional source additions.

- [ ] **Step 1: Run targeted backend and frontend tests plus the full frontend test file.**
- [ ] **Step 2: Run the production frontend build.**
- [ ] **Step 3: Restart only `huabang-backend`; verify it is active.**
- [ ] **Step 4: Call the authenticated production endpoint with a unique verification book, then query its accounts and fiscal periods and delete nothing.**
- [ ] **Step 5: Review the diff for authorization, legacy-data isolation, validation, and unnecessary changes.**
