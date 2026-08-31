-- ============================================================================
-- Bubble↔Rowboat sync (Phase 2): outbox + emit trigger + loop-prevention GUC
-- ============================================================================
-- DB side of the bidirectional sync, modeled on marketing/db/004_sync_triggers.sql
-- but SIMPLER (one table public.ideas, no fan-out, no audit_log):
--
--   1. public.ideas_sync_outbox  — append-only log of every ideas change.
--      Worker A (DB->FS) drains rows WHERE applied_at IS NULL.
--   2. emit_ideas_sync_event()   — AFTER INSERT/UPDATE/DELETE on public.ideas.
--      Resolves idea_id (the row) + bubble_id (parent, or self if top-level),
--      writes one outbox row, pg_notify('vibemind_ideas_sync','').
--   3. Loop prevention: session-GUC vibemind.sync_origin. Worker B (FS->DB)
--      sets set_config('vibemind.sync_origin','fs',true) in the SAME tx as its
--      write → the trigger sees 'fs' and skips emit → no echo back to FS.
--   4. mark_outbox_applied(uuid[]) — Worker A marks rows after a successful write.
--
-- Coexists with trg_ideas_touch_updated_at (BEFORE UPDATE, from the columns
-- migration): BEFORE runs first, so the outbox payload carries the fresh
-- updated_at (the conflict-ordering key for Phase 3 LWW).
--
-- Apply (PostgREST cannot run DDL — via docker-exec psql; MSYS_NO_PATHCONV=1 on
-- Git-Bash so the /tmp path is not mangled to a Windows path):
--   docker cp 20260610_ideas_sync_triggers.sql <supabase-db>:/tmp/
--   MSYS_NO_PATHCONV=1 docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/20260610_ideas_sync_triggers.sql

BEGIN;

-- ─── 1. Outbox ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ideas_sync_outbox (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id     text NOT NULL,                 -- affected idea (= public.ideas.id)
    bubble_id   text,                           -- owning bubble (parent_id, or id if top-level)
    operation   text NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    payload     jsonb NOT NULL,                 -- full NEW row (or OLD on DELETE)
    origin      text NOT NULL DEFAULT 'db',     -- 'db' (real change) or skipped if 'fs'
    emitted_at  timestamptz DEFAULT now(),
    applied_at  timestamptz                     -- NULL = not yet picked up by Worker A
);
CREATE INDEX IF NOT EXISTS idx_ideas_outbox_unapplied ON public.ideas_sync_outbox(emitted_at)
    WHERE applied_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ideas_outbox_idea ON public.ideas_sync_outbox(idea_id);

COMMENT ON TABLE public.ideas_sync_outbox IS
    'Append-only log of public.ideas changes for the bubble↔Rowboat sync. '
    'Worker A drains rows where applied_at IS NULL. NOT in the realtime publication.';

-- ─── 2. Emit function with loop-prevention ───────────────────────────────
CREATE OR REPLACE FUNCTION public.emit_ideas_sync_event() RETURNS trigger AS $$
DECLARE
    origin_tag   text;
    payload_json jsonb;
    v_idea_id    text;
    v_bubble_id  text;
BEGIN
    -- Skip emit if this change came from a Worker-B apply (loop prevention).
    BEGIN
        origin_tag := current_setting('vibemind.sync_origin', true);
    EXCEPTION WHEN OTHERS THEN
        origin_tag := NULL;
    END;
    IF origin_tag = 'fs' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    IF TG_OP = 'DELETE' THEN
        payload_json := to_jsonb(OLD);
    ELSE
        payload_json := to_jsonb(NEW);
    END IF;

    v_idea_id   := payload_json->>'id';
    -- owning bubble: parent_id if a child idea, else the idea is itself a bubble
    v_bubble_id := COALESCE(payload_json->>'parent_id', v_idea_id);

    INSERT INTO public.ideas_sync_outbox
        (idea_id, bubble_id, operation, payload, origin)
    VALUES
        (v_idea_id, v_bubble_id, TG_OP, payload_json, 'db');

    PERFORM pg_notify('vibemind_ideas_sync', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- ─── 3. Single AFTER trigger on public.ideas ─────────────────────────────
DROP TRIGGER IF EXISTS trg_emit_ideas_sync ON public.ideas;
CREATE TRIGGER trg_emit_ideas_sync
    AFTER INSERT OR UPDATE OR DELETE ON public.ideas
    FOR EACH ROW EXECUTE FUNCTION public.emit_ideas_sync_event();

-- ─── 4. mark_outbox_applied (Worker A) ───────────────────────────────────
CREATE OR REPLACE FUNCTION public.mark_ideas_outbox_applied(p_ids uuid[])
RETURNS integer AS $$
DECLARE n integer;
BEGIN
    UPDATE public.ideas_sync_outbox SET applied_at = now()
    WHERE id = ANY(p_ids) AND applied_at IS NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- ────────────────────────────────────────────────────────────────────────
-- Smoke test (manual):
--   UPDATE public.ideas SET score=score WHERE id=(SELECT id FROM public.ideas LIMIT 1);
--   SELECT idea_id, bubble_id, operation, origin FROM public.ideas_sync_outbox
--     ORDER BY emitted_at DESC LIMIT 1;   -- 1 row, origin='db'
--   -- loop-prevention (should produce NO new row):
--   BEGIN; SELECT set_config('vibemind.sync_origin','fs',true);
--   UPDATE public.ideas SET score=score WHERE id=(SELECT id FROM public.ideas LIMIT 1); COMMIT;
-- ────────────────────────────────────────────────────────────────────────
