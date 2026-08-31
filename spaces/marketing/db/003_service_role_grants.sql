-- ============================================================================
-- Marketing-Ops: explicit service_role grants
-- ============================================================================
-- Follow-up to 002_rls_baseline.sql: the global REVOKE in 002 was too
-- aggressive — it removed service_role's inherited schema USAGE too, so
-- ANY connection (including service_role) got "permission denied for
-- schema marketing" on a SET ROLE test.
--
-- This migration re-grants the service_role explicitly. It keeps the
-- anon/authenticated lockdown — those still have zero grants.
--
-- Apply:
--   docker cp 003_service_role_grants.sql vibemind_supabase-db.1.<id>:/tmp/
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -f /tmp/003_service_role_grants.sql
--
-- Verify (all three SET ROLE tests give expected result):
--   SET ROLE anon;          SELECT COUNT(*) FROM marketing.audiences; -- → permission denied
--   SET ROLE authenticated; SELECT COUNT(*) FROM marketing.audiences; -- → permission denied
--   SET ROLE service_role;  SELECT COUNT(*) FROM marketing.audiences; -- → 0 (success)

BEGIN;

GRANT USAGE ON SCHEMA marketing TO service_role;
GRANT ALL ON ALL TABLES    IN SCHEMA marketing TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA marketing TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA marketing TO service_role;

-- Future tables: same grant pattern
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing GRANT ALL ON TABLES    TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing GRANT ALL ON FUNCTIONS TO service_role;

-- Audit
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:003',
    'rls.service_role.grant',
    'marketing.*',
    jsonb_build_object(
        'role', 'service_role',
        'grants', ARRAY['USAGE on schema', 'ALL on tables', 'ALL on sequences', 'ALL on functions'],
        'default_privileges', true,
        'phase', 1,
        'follow_up_to', 'migration:002'
    )
);

COMMIT;
