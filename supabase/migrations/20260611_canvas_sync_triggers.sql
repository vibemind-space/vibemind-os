-- ============================================================================
-- Canvas↔Rowboat sync (Phase A): outbox + emit trigger + loop-prevention GUC
-- ============================================================================
-- DB side of the canvas-node bidirectional sync, a 1:1 fork of
-- 20260610_ideas_sync_triggers.sql for public.canvas_nodes:
--
--   1. public.canvas_sync_outbox  — append-only log of every canvas_nodes change.
--      Worker A (DB->FS) drains rows WHERE applied_at IS NULL.
--   2. emit_canvas_sync_event()   — AFTER INSERT/UPDATE/DELETE on canvas_nodes.
--      Resolves node_id (the row) + bubble_id (= linked_idea_id), writes one
--      outbox row, pg_notify('vibemind_canvas_sync','').
--      SCOPE: nodes with linked_idea_id IS NULL are NOT published (no .md exists
--      for them — publish_bubble only renders nodes linked to a bubble), so the
--      emit skips them entirely.
--   3. Loop prevention: the SAME session-GUC vibemind.sync_origin as ideas.
--      Worker B / the reformat drainer set set_config('vibemind.sync_origin',
--      'fs',true) in the SAME tx as their write → the trigger sees 'fs' and
--      skips emit → no echo back to FS.
--   4. mark_canvas_outbox_applied(uuid[]) — Worker A marks rows after a write.
--
-- Coexists with trg_canvas_touch_updated_at (BEFORE UPDATE, from the columns
-- migration): BEFORE runs first, so the outbox payload carries the fresh
-- updated_at (the LWW conflict-ordering key).
--
-- Apply (PostgREST cannot run DDL — via docker-exec psql; MSYS_NO_PATHCONV=1 on
-- Git-Bash so the /tmp path is not mangled to a Windows path):
--   docker cp 20260611_canvas_sync_triggers.sql <supabase-db>:/tmp/
--   MSYS_NO_PATHCONV=1 docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/20260611_canvas_sync_triggers.sql

BEGIN;

-- ─── 1. Outbox ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.canvas_sync_outbox (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id     text NOT NULL,                 -- affected node (= public.canvas_nodes.id)
    bubble_id   text,                           -- owning bubble (= linked_idea_id)
    operation   text NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    payload     jsonb NOT NULL,                 -- full NEW row (or OLD on DELETE)
    origin      text NOT NULL DEFAULT 'db',     -- 'db' (real change) or skipped if 'fs'
    emitted_at  timestamptz DEFAULT now(),
    applied_at  timestamptz                     -- NULL = not yet picked up by Worker A
);
CREATE INDEX IF NOT EXISTS idx_canvas_outbox_unapplied ON public.canvas_sync_outbox(emitted_at)
    WHERE applied_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_canvas_outbox_node ON public.canvas_sync_outbox(node_id);

COMMENT ON TABLE public.canvas_sync_outbox IS
    'Append-only log of public.canvas_nodes changes for the canvas↔Rowboat sync. '
    'Worker A drains rows where applied_at IS NULL. NOT in the realtime publication.';

-- ─── 2. Emit function with loop-prevention + NULL-bubble skip ─────────────
CREATE OR REPLACE FUNCTION public.emit_canvas_sync_event() RETURNS trigger AS $$
DECLARE
    origin_tag   text;
    payload_json jsonb;
    v_node_id    text;
    v_bubble_id  text;
BEGIN
    -- Skip emit if this change came from a Worker-B / drainer apply (loop prevention).
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

    v_bubble_id := payload_json->>'linked_idea_id';
    -- SCOPE: nodes not linked to a bubble have no .md — nothing to sync.
    IF v_bubble_id IS NULL THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    v_node_id := payload_json->>'id';

    INSERT INTO public.canvas_sync_outbox
        (node_id, bubble_id, operation, payload, origin)
    VALUES
        (v_node_id, v_bubble_id, TG_OP, payload_json, 'db');

    PERFORM pg_notify('vibemind_canvas_sync', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- ─── 3. Single AFTER trigger on public.canvas_nodes ──────────────────────
DROP TRIGGER IF EXISTS trg_emit_canvas_sync ON public.canvas_nodes;
CREATE TRIGGER trg_emit_canvas_sync
    AFTER INSERT OR UPDATE OR DELETE ON public.canvas_nodes
    FOR EACH ROW EXECUTE FUNCTION public.emit_canvas_sync_event();

-- ─── 4. mark_canvas_outbox_applied (Worker A) ────────────────────────────
CREATE OR REPLACE FUNCTION public.mark_canvas_outbox_applied(p_ids uuid[])
RETURNS integer AS $$
DECLARE n integer;
BEGIN
    UPDATE public.canvas_sync_outbox SET applied_at = now()
    WHERE id = ANY(p_ids) AND applied_at IS NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- ────────────────────────────────────────────────────────────────────────
-- Smoke test (manual) — pick a node WITH linked_idea_id:
--   UPDATE public.canvas_nodes SET content=content WHERE id='<node>';
--   SELECT node_id, bubble_id, operation, origin FROM public.canvas_sync_outbox
--     ORDER BY emitted_at DESC LIMIT 1;   -- 1 row, origin='db'
--   -- loop-prevention (should produce NO new row):
--   BEGIN; SELECT set_config('vibemind.sync_origin','fs',true);
--   UPDATE public.canvas_nodes SET content=content WHERE id='<node>'; COMMIT;
--   -- NULL-bubble skip (should produce NO row):
--   UPDATE public.canvas_nodes SET content=content WHERE linked_idea_id IS NULL LIMIT-via-subquery;
-- ────────────────────────────────────────────────────────────────────────
