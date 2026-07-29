# Finance V2 Platform Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Finance V2 use Huabang platform roles and permissions for all UI and API access.

**Architecture:** Keep JWT identity and all role/permission records in the existing `sys` schema. Introduce two Finance V2 permission codes, require both the `finance_manager` role and the matching permission for non-admin users, and retain feature gates as a separate accounting-write safety layer.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, PostgreSQL, Vue 3, Pinia, Node test runner, pytest.

## Global Constraints

- V2 API routes stay under `/api/v1/finance-center/v2`; UI routes stay under `/app/finance-center`.
- Only `finance_manager` and `super_admin` gain V2 access in this release.
- Do not create an independent account or authorization table.
- Feature gates remain closed until final cutover evidence is complete.
- Seed operations are idempotent and must not change unrelated users, roles or permissions.

---

### Task 1: Define and test central Finance V2 access rules

**Files:**
- Create: `backend/app/services/finance_v2/platform_permissions.py`
- Create: `backend/tests/test_finance_v2_platform_permissions.py`

**Interfaces:**
- Produces `FINANCE_MANAGER_ROLE`, `FINANCE_V2_READ_PERMISSION`, `FINANCE_V2_WRITE_PERMISSION`, and `assert_finance_v2_access(...)`.

- [ ] **Step 1: Write failing tests** for a finance manager with a required permission, a user missing the finance role, a finance manager missing a permission, and a super administrator.
- [ ] **Step 2: Run** `python -m pytest tests/test_finance_v2_platform_permissions.py -q` and confirm failure because the service is absent.
- [ ] **Step 3: Implement** a pure authorization function that allows administrators, otherwise requires `finance_manager` and the requested central permission.
- [ ] **Step 4: Re-run** the test and confirm all cases pass.
- [ ] **Step 5: Commit** the service and test.

### Task 2: Wire every Finance V2 API route to central permissions

**Files:**
- Modify: `backend/app/api/v1/deps.py`
- Modify: `backend/app/api/v1/finance_v2.py`
- Modify: `backend/tests/test_finance_v2_route_registration.py`

**Interfaces:**
- Consumes `assert_finance_v2_access` and the existing JWT/current-user dependencies.
- Produces `require_finance_v2_permission(permission_code)` for FastAPI dependencies.

- [ ] **Step 1: Write a failing route test** that asserts GET routes require `finance:center:view` and POST command routes require `finance:center:operate`.
- [ ] **Step 2: Run** `python -m pytest tests/test_finance_v2_route_registration.py -q` and confirm the dependency assertions fail.
- [ ] **Step 3: Implement** central permission loading and a Finance V2 dependency without changing generic platform authorization semantics.
- [ ] **Step 4: Replace** V2 route role-only dependencies with the read or write dependency.
- [ ] **Step 5: Re-run** the route and full Finance V2 tests; commit.

### Task 3: Seed and expose the permissions through the platform

**Files:**
- Create: `backend/scripts/seed_finance_v2_permissions.py`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/config/financeCenterModules.ts`
- Modify: `frontend/tests/finance-v2-core.test.cjs`

**Interfaces:**
- Seed script creates `finance_manager`, two `sys_permission` records and their two `sys_role_permission` links with PostgreSQL conflict-safe SQL.

- [ ] **Step 1: Write failing tests** for the script's idempotent role/permission set and the frontend's `finance:center:view` route/navigation gate.
- [ ] **Step 2: Run** targeted backend and frontend tests and confirm failures.
- [ ] **Step 3: Implement** the seed script and replace the old generic finance permission in the V2 UI route/navigation gate.
- [ ] **Step 4: Run** targeted tests, backend Finance V2 suite, frontend type-check and production build.
- [ ] **Step 5: Commit** the complete integration.

### Task 4: Recovery-copy execution evidence

**Files:**
- Modify: `docs/finance/v2-0-evidence-register.md`
- Modify: `docs/finance/v2-0-release-baseline.md`

- [ ] **Step 1: Create a PostgreSQL recovery copy** from `huabang_ai` without stopping production.
- [ ] **Step 2: Run** role bootstrap, all Alembic migrations, the platform-permission seed and Kingdee history dry run/import validation on the recovery copy.
- [ ] **Step 3: Record** exact database name, commands, row counts, restore time, test results, failures and Go/No-Go status.
- [ ] **Step 4: Commit** evidence only after the checks finish.
