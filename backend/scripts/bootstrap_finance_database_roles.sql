-- Finance V2 PostgreSQL role bootstrap, to be executed only by a database
-- administrator.  It creates no password and changes no application config.
--
-- MUST be run by a PostgreSQL database administrator after a confirmed backup
-- and before the first Finance V2 Alembic migration.  Do not run it through the
-- application account.  Passwords and connection strings are intentionally not
-- present in this repository; inject them from the approved secret store.
--
-- Run with: psql -v ON_ERROR_STOP=1 -d <database> -f bootstrap_finance_database_roles.sql

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_schema_owner') THEN
        CREATE ROLE fin_schema_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_migrator') THEN
        CREATE ROLE fin_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_app') THEN
        CREATE ROLE fin_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_history_importer') THEN
        CREATE ROLE fin_history_importer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_readonly_auditor') THEN
        CREATE ROLE fin_readonly_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE fin_schema_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE fin_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE fin_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE fin_history_importer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE fin_readonly_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

-- A table/sequence owner retains implicit full access even after a REVOKE.
-- Refuse a partial retrofit rather than claiming this script can remove that
-- implicit access.  A DBA must transfer or rebuild any pre-existing V2 objects
-- under the owner role in a separately reviewed change.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class relation
        JOIN pg_namespace schema ON schema.oid = relation.relnamespace
        WHERE schema.nspname IN ('fin_current', 'fin_history', 'fin_read')
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
          AND pg_get_userbyid(relation.relowner) <> 'fin_schema_owner'
    ) THEN
        RAISE EXCEPTION
            'existing Finance V2 objects are not owned by fin_schema_owner; aborting least-privilege retrofit';
    END IF;
END
$$;

-- The migration connection must use `SET ROLE fin_schema_owner` (for example
-- through PGOPTIONS) while running Alembic.  The owner itself cannot log in.
GRANT fin_schema_owner TO fin_migrator;
REVOKE fin_schema_owner FROM fin_app, fin_history_importer, fin_readonly_auditor;

-- Database CONNECT is deliberately not changed here: PostgreSQL requires a
-- literal database identifier in GRANT/REVOKE, while this checked-in script
-- must remain reusable.  The administrator grants CONNECT explicitly during
-- the secure environment-specific invocation described at the end.

CREATE SCHEMA IF NOT EXISTS fin_current AUTHORIZATION fin_schema_owner;
CREATE SCHEMA IF NOT EXISTS fin_history AUTHORIZATION fin_schema_owner;
CREATE SCHEMA IF NOT EXISTS fin_read AUTHORIZATION fin_schema_owner;
ALTER SCHEMA fin_current OWNER TO fin_schema_owner;
ALTER SCHEMA fin_history OWNER TO fin_schema_owner;
ALTER SCHEMA fin_read OWNER TO fin_schema_owner;

REVOKE ALL ON SCHEMA fin_current, fin_history, fin_read FROM PUBLIC;
REVOKE ALL ON SCHEMA fin_current, fin_history, fin_read FROM fin_app, fin_history_importer, fin_readonly_auditor;
GRANT USAGE ON SCHEMA fin_current TO fin_app;
GRANT USAGE ON SCHEMA fin_history TO fin_history_importer;
GRANT USAGE ON SCHEMA fin_read TO fin_app, fin_history_importer, fin_readonly_auditor;

-- Default privileges are for objects that the owner creates after this script.
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_current REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_history REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_read REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_current GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fin_app;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_current GRANT USAGE, SELECT ON SEQUENCES TO fin_app;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_history GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fin_history_importer;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_history GRANT USAGE, SELECT ON SEQUENCES TO fin_history_importer;
ALTER DEFAULT PRIVILEGES FOR ROLE fin_schema_owner IN SCHEMA fin_read GRANT SELECT ON TABLES TO fin_app, fin_history_importer, fin_readonly_auditor;

-- Also apply the least-privilege baseline if the schemas/tables already exist.
REVOKE ALL ON ALL TABLES IN SCHEMA fin_current FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_current FROM fin_history_importer;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_current FROM fin_readonly_auditor;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_current FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_current FROM fin_history_importer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_current FROM fin_readonly_auditor;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_history FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_history FROM fin_app;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_history FROM fin_readonly_auditor;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_history FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_history FROM fin_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_history FROM fin_readonly_auditor;
REVOKE ALL ON ALL TABLES IN SCHEMA fin_read FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_read FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_read FROM fin_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_read FROM fin_history_importer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA fin_read FROM fin_readonly_auditor;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA fin_current TO fin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fin_current TO fin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA fin_history TO fin_history_importer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fin_history TO fin_history_importer;
GRANT SELECT ON ALL TABLES IN SCHEMA fin_read TO fin_app, fin_readonly_auditor;

COMMIT;

-- Required secure follow-up (not executable without the target database name
-- and secrets):
--   1. GRANT CONNECT ON DATABASE <database> TO fin_migrator, fin_app,
--      fin_history_importer, fin_readonly_auditor;
--   2. Set a unique secret for every LOGIN role in the approved secret store;
--   3. Configure Alembic as fin_migrator with `SET ROLE fin_schema_owner`;
--   4. Configure the web service as fin_app and the one-shot loader as
--      fin_history_importer; then run verify_finance_database_roles.py.
