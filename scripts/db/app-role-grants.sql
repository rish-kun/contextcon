-- Privileges of the API's runtime database role (dealproof_app in production).
--
-- The runtime role reads and writes rows and nothing else: no DDL, no TRUNCATE, no
-- TRIGGER (so it cannot disable the immutability triggers), no REFERENCES, and no
-- writes to alembic_version. The schema owner keeps DDL and runs migrations through
-- DATABASE_MIGRATION_URL.
--
-- Applied by scripts/db/provision-app-role.py (production) and by the API tests,
-- which run the app's database tests as a role holding exactly these grants.
-- Run it as the schema owner. Placeholders are filled with quoted identifiers:
--   {app}       the runtime role
--   {owner}     the role that owns the tables and runs migrations
--   {database}  the database
-- Every statement is idempotent.

GRANT CONNECT ON DATABASE {database} TO {app};
GRANT USAGE ON SCHEMA public TO {app};
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Existing tables and sequences.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app};
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {app};

-- Tables and sequences later migrations create (as {owner}).
ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app};
ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO {app};

-- The app may read the schema version (RUN_MIGRATIONS=verify) but never change it.
DO $$
BEGIN
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        EXECUTE 'REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM {app}';
    END IF;
END
$$;
