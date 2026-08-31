-- ============================================================================
-- Marketing-Ops RLS Baseline (Phase 1)
-- ============================================================================
-- Phase 1 lockdown: only the `service_role` role (which inherently bypasses
-- RLS in Supabase) reads/writes marketing.* data. The `anon` and
-- `authenticated` roles get NO grants at all — any PostgREST request that
-- arrives via the anon-key or a user-JWT cannot even SELECT the schema.
--
-- Why this matters: Supabase REST is reachable on host :54321. Any leak of
-- the anon-key (e.g. into committed frontend code, demo screenshots, a
-- public OpenFang agent that introspects the schema) would otherwise expose
-- the entire marketing dataset — including 50+ test recipients today and
-- real DSGVO-relevant recipient PII tomorrow.
--
-- The `REVOKE ALL ON SCHEMA` + `REVOKE ALL ON ALL TABLES` is the REAL
-- protection here. `ENABLE ROW LEVEL SECURITY` + the service_role policy
-- is symbolic — service_role bypasses RLS anyway. But we enable RLS now
-- so that the moment we add a Phase-2 user policy, we don't accidentally
-- expose data via a forgotten `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`.
--
-- Apply with:
--   docker cp 002_rls_baseline.sql vibemind_supabase-db.1.<id>:/tmp/
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -f /tmp/002_rls_baseline.sql
--
-- Verify (must return 13 rows, all relrowsecurity = t):
--   SELECT relname, relrowsecurity FROM pg_class
--    WHERE relnamespace = 'marketing'::regnamespace AND relkind = 'r'
--    ORDER BY relname;
--
-- Rollback (re-grant + disable RLS):
--   GRANT USAGE ON SCHEMA marketing TO anon, authenticated;
--   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA marketing TO authenticated;
--   ALTER TABLE marketing.<each> DISABLE ROW LEVEL SECURITY;

BEGIN;

-- ============================================================================
-- 1) Revoke schema + table access from PostgREST-facing roles
-- ============================================================================
-- This is the real lockdown. anon = unauthenticated PostgREST requests.
-- authenticated = any role with a valid auth.users JWT. Neither should
-- touch marketing.* in Phase 1.

REVOKE ALL ON SCHEMA marketing FROM anon, authenticated, PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA marketing FROM anon, authenticated, PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA marketing FROM anon, authenticated, PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA marketing FROM anon, authenticated, PUBLIC;

-- service_role keeps full access (it's the postgrest-superuser role).
-- supabase_admin keeps full access (DDL ownership).
-- No explicit GRANT needed — service_role is set up as DEFAULT in Supabase.

-- Default privileges for FUTURE tables in this schema: same lockdown.
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA marketing REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- ============================================================================
-- 2) Enable Row Level Security on all 13 tables
-- ============================================================================
-- Even though service_role bypasses RLS, enabling it now means Phase-2
-- user policies (when added) actually take effect. If we forget to
-- enable RLS on a table later, any GRANT to authenticated would expose
-- the full table without policy filtering — a classic Supabase footgun.

ALTER TABLE marketing.accounts          ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.emails            ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.strategies        ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.runs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.tags              ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.email_tags        ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.audiences         ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.audience_members  ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.templates         ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.campaigns         ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.campaign_sends    ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.inbound_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing.audit_log         ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table-owner (otherwise owner sessions skip the policy
-- check, which would let a DDL-owner-connection read everything without
-- a policy match — relevant once Phase 2 has real user data).
ALTER TABLE marketing.accounts          FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.emails            FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.strategies        FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.runs              FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.tags              FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.email_tags        FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.audiences         FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.audience_members  FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.templates         FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.campaigns         FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.campaign_sends    FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.inbound_messages  FORCE ROW LEVEL SECURITY;
ALTER TABLE marketing.audit_log         FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- 3) Phase-2 user policies — placeholder, NOT activated yet
-- ============================================================================
-- These are the policies that will go live when Phase 2 (Supabase-Auth
-- multi-user) is rolled out. They're stored here as comments so the next
-- migration `003_rls_user_policies.sql` has a starting template.
--
-- Each marketing-ops resource should be tied to either:
--   a) created_by (uuid column referencing auth.users.id) for owner-CRUD
--   b) a shared-team membership table for collaborator access
--   c) public-read for safe metadata (e.g. templates marked is_public)
--
-- Example skeletons:
--
-- ALTER TABLE marketing.audiences ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES auth.users(id);
-- CREATE POLICY audiences_owner_all ON marketing.audiences
--   FOR ALL TO authenticated
--   USING (created_by = auth.uid())
--   WITH CHECK (created_by = auth.uid());
--
-- CREATE POLICY campaigns_owner_all ON marketing.campaigns
--   FOR ALL TO authenticated
--   USING (created_by = auth.uid())
--   WITH CHECK (created_by = auth.uid());
--
-- -- Templates: owner-CRUD plus public-read for is_public templates
-- CREATE POLICY templates_owner_all ON marketing.templates
--   FOR ALL TO authenticated
--   USING (created_by = auth.uid());
-- CREATE POLICY templates_public_read ON marketing.templates
--   FOR SELECT TO authenticated USING (is_public = true);
--
-- -- audit_log: write-only for owners, read for admins (admin role TBD)
-- CREATE POLICY audit_log_owner_write ON marketing.audit_log
--   FOR INSERT TO authenticated WITH CHECK (actor = 'user:' || auth.uid()::text);
-- (no SELECT policy = no one in `authenticated` can read it — only admin)

-- ============================================================================
-- 4) Audit-trail entry: record the migration
-- ============================================================================
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:002',
    'rls.baseline.apply',
    'marketing.*',
    jsonb_build_object(
        'tables_locked', 13,
        'roles_revoked', ARRAY['anon', 'authenticated', 'PUBLIC'],
        'force_rls', true,
        'phase', 1,
        'notes', 'service_role retains bypass; anon/authenticated have no grants. Phase-2 user policies pending.'
    )
);

COMMIT;

-- ============================================================================
-- Post-apply verification (run manually):
-- ============================================================================
-- 1. All 13 tables have RLS enabled:
--    SELECT relname, relrowsecurity, relforcerowsecurity
--    FROM pg_class
--    WHERE relnamespace = 'marketing'::regnamespace AND relkind = 'r'
--    ORDER BY relname;
--    -- Expected: 13 rows, both columns = t
--
-- 2. anon has no privileges on marketing.* tables:
--    SELECT table_name, privilege_type
--    FROM information_schema.table_privileges
--    WHERE table_schema='marketing' AND grantee='anon';
--    -- Expected: 0 rows
--
-- 3. The PostgREST anon endpoint can't even see the schema:
--    curl http://127.0.0.1:54321/rest/v1/marketing.audiences -H "apikey: <ANON_KEY>"
--    -- Expected: 401/403 OR "schema marketing not found" — never a row dump
-- ============================================================================
