-- Application DB role for RENZY production.
-- The trigger in orders migrations already makes order_events append-only; this also strips
-- UPDATE/DELETE/TRUNCATE privileges so a compromised app credential cannot rewrite history.
--
-- Apply as the database owner (or a superuser) on the managed Postgres instance AFTER migrations:
--
--   psql "$DATABASE_URL_OWNER" -v ON_ERROR_STOP=1 -f infra/db/roles.sql
--
-- Then point the app's DATABASE_URL at app_user (not the owner). Rotate the password immediately:
--
--   ALTER ROLE app_user PASSWORD '…long random…';
--
-- Replace the database name below if yours is not `renzy`.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'change-me-before-go-live';
    END IF;
END $$;

GRANT CONNECT ON DATABASE renzy TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_user;

-- Append-only event log (ADR-0001 / CLAUDE.md invariant 3).
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE order_events FROM app_user;

-- Confirm (should show INSERT + SELECT only for app_user on order_events):
--   \dp order_events
