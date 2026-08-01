# Huabang Full Finance Center

## Goal

Reproduce the complete Mumaren finance-center capability in Huabang, migrate the verified Kingdee history into a writable formal ledger, and preserve immutable source evidence.

## Phases

| Phase | Status | Evidence gate |
| --- | --- | --- |
| 1. Design and executable plan | complete | Design and implementation-plan commits exist |
| 2. Isolated workspace and baseline | complete | Existing tests/build characterized |
| 3. Finance models and migration | in_progress | Model tests pass and Alembic has one head |
| 4. Voucher lifecycle, ledger, history | pending | State, balance, idempotency, baseline tests pass |
| 5. Statements and operational modules | pending | Module/API tests pass with no placeholder routes |
| 6. Automation, permissions, and frontend | pending | Permission, type-check, build, and browser tests pass |
| 7. Trial migration and production rollout | pending | Backups verified and production acceptance recorded |

## Decisions

- Kingdee ODS/DWD remains immutable and is never written back.
- Formal accounting lives in a writable `fin` schema.
- Imported history starts posted and covered periods start closed.
- Business systems generate drafts only; finance users review and post.
- Statements remain pending until mappings and periods are complete.
- Production is gated by a verified backup, trial migration, one Alembic head, and full acceptance.

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| Parallel config probe returned exit 1 because optional config files were absent | 1 | Probe only existing files and continue |
| `alembic` executable was not on PATH during parallel baseline | 1 | Use `python -m alembic` from the backend environment |
| Full pytest collection lacked three required secrets in isolated worktree | 1 | Re-run with command-scoped non-production test values |
| Backend `alembic/` package shadowed installed Alembic when invoking Python CLI from backend cwd | 2 | Invoke CLI from repository root with `PYTHONPATH=backend` and explicit config path |
| Locked psycopg2-binary has no Python 3.14 wheel and local pg_config is absent | 1 | Rebuild project venv with an installed Python 3.11/3.12 runtime |
| Baseline full suite has 36 existing environment/data failures | 1 | Record 613 passing tests; isolate missing greenlet, local DB, and Windows encoding causes before feature tests |
| Docker CLI could not reach the stopped Docker Desktop engine | 1 | Start Docker Desktop locally, then use an isolated PostgreSQL 16 container |
| Existing Alembic chain cannot bootstrap a blank database because an early revision assumes `dim.dim_store` exists | 1 | Validate the production upgrade path by creating the current non-fin model schema, stamping `2d1f6a7b8c96`, then upgrading |
