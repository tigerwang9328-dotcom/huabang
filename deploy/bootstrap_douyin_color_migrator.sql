-- Run only through deploy/run_douyin_color_migrations.sh as the PostgreSQL OS role.
-- This role owns just the douyin schema. It is deliberately never granted finance access.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'huabang_douyin_migrator') THEN
        CREATE ROLE huabang_douyin_migrator NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS douyin AUTHORIZATION huabang_douyin_migrator;
REVOKE ALL ON SCHEMA douyin FROM PUBLIC;
GRANT USAGE ON SCHEMA douyin TO huabang;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA douyin TO huabang;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA douyin TO huabang;
ALTER DEFAULT PRIVILEGES FOR ROLE huabang_douyin_migrator IN SCHEMA douyin GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO huabang;
ALTER DEFAULT PRIVILEGES FOR ROLE huabang_douyin_migrator IN SCHEMA douyin GRANT USAGE, SELECT ON SEQUENCES TO huabang;
