"""
order_events is append-only, enforced by the database rather than by discipline (ADR-0001).

A trigger works on managed Postgres without a custom role. infra/db/roles.sql adds REVOKE on top
where the app connects with a dedicated role. Never edit this migration once it has run in production.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION order_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'order_events is append-only (ADR-0001): % is not allowed', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER order_events_no_update_delete
    BEFORE UPDATE OR DELETE ON order_events
    FOR EACH ROW EXECUTE FUNCTION order_events_append_only();
"""
# TRUNCATE is deliberately not trapped here: it is a table-owner privilege that infra/db/roles.sql
# revokes from the application role, and Django's test runner needs it to reset the test database.

BACKWARD = """
DROP TRIGGER IF EXISTS order_events_no_update_delete ON order_events;
DROP FUNCTION IF EXISTS order_events_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
