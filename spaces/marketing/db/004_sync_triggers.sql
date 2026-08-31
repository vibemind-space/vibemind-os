-- ============================================================================
-- Marketing-Ops Sync Triggers (Phase 3)
-- ============================================================================
-- Sets up the DB side of the bi-directional sync system:
--
--   1. marketing.sync_outbox table — append-only log of every relevant
--      change. Worker A LISTENs on a NOTIFY channel, dequeues from this
--      table, and updates the markdown vault.
--
--   2. Trigger function `emit_sync_event()` — fires on INSERT/UPDATE/DELETE
--      across all marketing.* tables. Resolves the affected `handle`,
--      writes one outbox row, emits pg_notify('marketing_sync', '').
--
--   3. Loop prevention: a session-scoped GUC `marketing.sync_origin`. When
--      Worker B writes back to the DB to propagate a FS-delete, it first
--      sets `SELECT set_config('marketing.sync_origin', 'fs', true)`. The
--      trigger checks this and skips outbox emit — no echo back to FS.
--
--   4. Triggers on ALL marketing.* tables (Felix-Entscheidung 2026-06-02:
--      "komplette infra"). Performance: Mailcow-Send-Volume is bounded
--      by loopback-block, real load is well below 1k events/min.
--
-- Apply:
--   docker cp 004_sync_triggers.sql <supabase-db>:/tmp/
--   docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/004_sync_triggers.sql
--
-- Verify:
--   - INSERT INTO marketing.accounts (handle) VALUES ('trig_test')
--     → SELECT * FROM marketing.sync_outbox ORDER BY emitted_at DESC LIMIT 1
--     → 1 row, table='accounts', operation='INSERT', origin='db'
--   - SELECT set_config('marketing.sync_origin', 'fs', true);
--     UPDATE marketing.accounts SET niche='X' WHERE handle='trig_test';
--     → no new outbox row

BEGIN;

-- ─── 1. Outbox table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.sync_outbox (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    affected_handle text,                    -- resolved 'handle' the markdown file refers to
    table_name   text NOT NULL,
    row_key      text NOT NULL,              -- table-specific primary key (handle/email/uuid)
    operation    text NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    payload      jsonb NOT NULL,             -- full row content (or OLD on DELETE)
    origin       text NOT NULL DEFAULT 'db', -- 'db' or 'fs'
    emitted_at   timestamptz DEFAULT now(),
    applied_at   timestamptz                 -- NULL = not yet picked up by Worker A
);
CREATE INDEX IF NOT EXISTS idx_outbox_unapplied ON marketing.sync_outbox(emitted_at)
    WHERE applied_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_outbox_handle ON marketing.sync_outbox(affected_handle);

GRANT ALL ON marketing.sync_outbox TO service_role;

COMMENT ON TABLE marketing.sync_outbox IS
    'Append-only log of marketing.* changes. Worker A drains rows where applied_at IS NULL.';

-- ─── 2. Helper: resolve the affected handle for any marketing.* row ──────
CREATE OR REPLACE FUNCTION marketing._resolve_handle(
    p_table text, p_row jsonb
) RETURNS text AS $$
DECLARE
    h text;
BEGIN
    -- Each table has a different path to .handle:
    CASE p_table
        WHEN 'accounts' THEN
            h := p_row->>'handle';
        WHEN 'emails' THEN
            h := p_row->>'handle';
        WHEN 'email_tags' THEN
            SELECT handle INTO h FROM marketing.emails WHERE email = p_row->>'email' LIMIT 1;
        WHEN 'audience_members' THEN
            SELECT handle INTO h FROM marketing.emails WHERE email = p_row->>'email' LIMIT 1;
        WHEN 'campaign_sends' THEN
            SELECT handle INTO h FROM marketing.emails WHERE email = p_row->>'email' LIMIT 1;
        WHEN 'inbound_messages' THEN
            SELECT handle INTO h FROM marketing.emails WHERE email = p_row->>'from_email' LIMIT 1;
        WHEN 'tags' THEN
            -- Tag changes affect every account that has emails tagged with this tag
            -- Worker A handles the fan-out — store NULL here, let Worker requeue per-handle
            h := NULL;
        WHEN 'audiences' THEN
            -- Same — affects every member
            h := NULL;
        WHEN 'campaigns' THEN
            h := NULL;  -- affects every recipient
        WHEN 'templates' THEN
            h := NULL;  -- templates don't affect specific people
        WHEN 'strategies' THEN
            h := NULL;  -- strategies affect every email with that strategy_id
        WHEN 'runs' THEN
            h := NULL;  -- runs don't appear in per-person markdown
        ELSE
            h := NULL;
    END CASE;
    RETURN h;
END;
$$ LANGUAGE plpgsql;

-- ─── 3. Emit function with loop-prevention ───────────────────────────────
CREATE OR REPLACE FUNCTION marketing.emit_sync_event() RETURNS trigger AS $$
DECLARE
    origin_tag    text;
    affected_h    text;
    row_key_val   text;
    payload_json  jsonb;
BEGIN
    -- Skip emit if this change is the result of a Worker-B apply (loop prevention)
    BEGIN
        origin_tag := current_setting('marketing.sync_origin', true);
    EXCEPTION WHEN OTHERS THEN
        origin_tag := NULL;
    END;
    IF origin_tag = 'fs' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    -- Determine the row payload + key + affected_handle
    IF TG_OP = 'DELETE' THEN
        payload_json := to_jsonb(OLD);
    ELSE
        payload_json := to_jsonb(NEW);
    END IF;

    affected_h := marketing._resolve_handle(TG_TABLE_NAME, payload_json);

    -- Pick a stable row-key per table (PK or natural key)
    CASE TG_TABLE_NAME
        WHEN 'accounts'         THEN row_key_val := payload_json->>'handle';
        WHEN 'emails'           THEN row_key_val := payload_json->>'email';
        WHEN 'email_tags'       THEN row_key_val := (payload_json->>'email') || '|' || (payload_json->>'tag_id');
        WHEN 'audience_members' THEN row_key_val := (payload_json->>'audience_id') || '|' || (payload_json->>'email');
        WHEN 'campaign_sends'   THEN row_key_val := payload_json->>'id';
        WHEN 'inbound_messages' THEN row_key_val := payload_json->>'id';
        WHEN 'tags'             THEN row_key_val := payload_json->>'id';
        WHEN 'audiences'        THEN row_key_val := payload_json->>'id';
        WHEN 'campaigns'        THEN row_key_val := payload_json->>'id';
        WHEN 'templates'        THEN row_key_val := payload_json->>'id';
        WHEN 'strategies'       THEN row_key_val := payload_json->>'id';
        WHEN 'runs'             THEN row_key_val := payload_json->>'id';
        ELSE row_key_val := COALESCE(payload_json->>'id', payload_json::text);
    END CASE;

    INSERT INTO marketing.sync_outbox
        (affected_handle, table_name, row_key, operation, payload, origin)
    VALUES
        (affected_h, TG_TABLE_NAME, row_key_val, TG_OP, payload_json, 'db');

    -- Wake the worker
    PERFORM pg_notify('marketing_sync', '');

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- ─── 4. Attach triggers to every marketing.* business table ──────────────
DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'accounts', 'emails', 'email_tags',
        'audiences', 'audience_members',
        'tags',
        'templates',
        'campaigns', 'campaign_sends',
        'inbound_messages',
        'strategies', 'runs'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_emit_sync_%I ON marketing.%I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_emit_sync_%I '
            'AFTER INSERT OR UPDATE OR DELETE ON marketing.%I '
            'FOR EACH ROW EXECUTE FUNCTION marketing.emit_sync_event()',
            t, t
        );
    END LOOP;
END $$;

-- ─── 5. Helper: mark outbox rows as applied (Worker A calls this) ────────
CREATE OR REPLACE FUNCTION marketing.mark_outbox_applied(p_ids uuid[])
RETURNS integer AS $$
DECLARE
    n integer;
BEGIN
    UPDATE marketing.sync_outbox
    SET applied_at = now()
    WHERE id = ANY(p_ids) AND applied_at IS NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

-- ─── 6. Audit ────────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:004',
    'sync.triggers.install',
    'marketing.*',
    jsonb_build_object(
        'tables_with_triggers', 12,
        'outbox_table', 'marketing.sync_outbox',
        'notify_channel', 'marketing_sync',
        'loop_prevention', 'session GUC marketing.sync_origin = fs skips emit'
    )
);

COMMIT;

-- ────────────────────────────────────────────────────────────────────────
-- Smoke test (manual, after apply):
--   -- Should produce 1 outbox row, origin='db':
--   INSERT INTO marketing.accounts (handle, display_name) VALUES ('trg_test', 'Trigger Test');
--   SELECT id, table_name, operation, origin, affected_handle FROM marketing.sync_outbox
--     ORDER BY emitted_at DESC LIMIT 1;
--
--   -- Should NOT produce an outbox row (origin tag suppresses):
--   BEGIN;
--   SELECT set_config('marketing.sync_origin', 'fs', true);
--   UPDATE marketing.accounts SET niche='X' WHERE handle='trg_test';
--   COMMIT;
--   -- (no new outbox row)
--
--   -- Cleanup:
--   DELETE FROM marketing.accounts WHERE handle='trg_test';
-- ────────────────────────────────────────────────────────────────────────
