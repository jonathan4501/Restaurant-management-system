-- Optional hardening where the database allows a dedicated application role.
-- The trigger in orders/0002 already makes order_events append-only; this removes the privilege too.
-- Run as the database owner after migrations:
--   psql "$DATABASE_URL" -f infra/db/roles.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'change-me';
    END IF;
END $$;

GRANT CONNECT ON DATABASE renzy TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

REVOKE UPDATE, DELETE, TRUNCATE ON order_events FROM app_user;
