-- ============================================================================
-- Bubble↔Rowboat sync (Phase 1): change-tracking columns on public.ideas
-- ============================================================================
-- Adds the timestamp the bidirectional sync needs for conflict ordering (LWW):
--
--   updated_at     : bumped on every row UPDATE by a BEFORE-UPDATE trigger.
--                    The conflict key — Worker B compares it to the file's
--                    frontmatter last_synced_at to decide FS-edit vs DB-wins.
--   last_synced_at : timestamp of the last successful DB->FS render (set by
--                    Worker A). NULL = never rendered.
--
-- NOTE: no sync_id column — public.ideas.id is already a stable UUID-as-text PK
-- (init_vibemind.sql), reused as the markdown frontmatter `idea_id`. No backfill
-- of a second key needed (unlike marketing.accounts which had a renameable handle).
--
-- Apply (PostgREST cannot run DDL — must go via docker-exec psql):
--   docker cp 20260610_ideas_sync_columns.sql <supabase-db>:/tmp/
--   docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/20260610_ideas_sync_columns.sql
-- Then reload PostgREST's schema cache:
--   docker exec <supabase-db> psql -U supabase_admin -d postgres -c "NOTIFY pgrst, 'reload schema';"

BEGIN;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS updated_at     timestamptz DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_synced_at timestamptz;

-- Backfill: existing rows get updated_at from created_at (or now() if null).
UPDATE public.ideas
    SET updated_at = COALESCE(updated_at, created_at, now())
    WHERE updated_at IS NULL;

-- BEFORE-UPDATE trigger: stamp updated_at on every change. Runs before the
-- AFTER-trigger outbox emit (Phase 2), so the outbox payload carries the fresh
-- timestamp. Guarded against the sync-origin GUC is NOT needed here — touching
-- updated_at on an FS-applied write is harmless (the write IS a real change).
CREATE OR REPLACE FUNCTION public.ideas_touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ideas_touch_updated_at ON public.ideas;
CREATE TRIGGER trg_ideas_touch_updated_at
    BEFORE UPDATE ON public.ideas
    FOR EACH ROW EXECUTE FUNCTION public.ideas_touch_updated_at();

COMMENT ON COLUMN public.ideas.updated_at IS
    'Bumped on every UPDATE by trg_ideas_touch_updated_at. Conflict-ordering '
    'key for the bubble↔Rowboat bidirectional sync (LWW).';
COMMENT ON COLUMN public.ideas.last_synced_at IS
    'Timestamp of the last successful DB->FS markdown render (set by the sync '
    'worker). NULL = never rendered to ~/.rowboat/knowledge/Projects/.';

COMMIT;

-- PostgREST schema-cache reload (run separately if applying this file alone):
NOTIFY pgrst, 'reload schema';
