-- ============================================================================
-- Canvas↔Rowboat sync (Phase A): reformat-jobs queue
-- ============================================================================
-- When a STRUCTURED canvas node (content_json IS NOT NULL) has its prose body
-- edited via the Rowboat Knowledge tab, Worker B writes the edit to the plain
-- `content` column (lossless) and ENQUEUES a job here. A dedicated debounced
-- drainer (worker_canvas_reformat.py) later regenerates content_json from the
-- edited content via the LLM formatter — OUT of the watchdog hot path, so a
-- blocking 3000-token LLM call never starves the file observer.
--
-- Debounce / coalescing: a partial UNIQUE index on (node_id) WHERE status =
-- 'pending' means rapid re-saves of the same node collapse onto ONE pending row
-- (Worker B uses INSERT ... ON CONFLICT DO UPDATE to bump enqueued_at). The
-- drainer only picks a job whose enqueued_at is older than the debounce window,
-- so a node still being typed into is not formatted until the user pauses.
--
-- prev_content_json holds the node's ORIGINAL content_json captured BEFORE the
-- edit (Worker B reads it in the same handler, before its content UPDATE). The
-- drainer writes it back as canvas_nodes.previous_content_json so the app's
-- "revert formatting" still restores the last good structured form.
--
-- NOTE: this table has NO sync trigger — it is internal plumbing, never rendered
-- to FS, so its writes do not need the GUC fence.
--
-- Apply (via docker-exec psql; MSYS_NO_PATHCONV=1 on Git-Bash):
--   docker cp 20260611_canvas_reformat_jobs.sql <supabase-db>:/tmp/
--   MSYS_NO_PATHCONV=1 docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/20260611_canvas_reformat_jobs.sql

BEGIN;

CREATE TABLE IF NOT EXISTS public.canvas_reformat_jobs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id           text NOT NULL,            -- public.canvas_nodes.id to reformat
    bubble_id         text,                      -- = linked_idea_id (for context/debug)
    target_format     text NOT NULL,            -- node_type at enqueue time (e.g. technical_specs, swot)
    prev_content_json jsonb,                    -- ORIGINAL content_json, captured BEFORE the edit (undo source)
    content_hash      text,                      -- hash of the edited content that triggered this job
    status            text NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','running','done','failed')),
    attempts          int NOT NULL DEFAULT 0,
    last_error        text,
    enqueued_at       timestamptz DEFAULT now(),
    started_at        timestamptz,
    finished_at       timestamptz
);

-- One LIVE pending job per node (debounce/coalesce key). Worker B's
-- INSERT ... ON CONFLICT (node_id) WHERE status='pending' DO UPDATE relies on
-- this partial unique index to collapse N rapid saves into one row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_canvas_reformat_pending
    ON public.canvas_reformat_jobs(node_id) WHERE status = 'pending';

-- Pickable-job index: the drainer scans pending jobs ordered by enqueued_at.
CREATE INDEX IF NOT EXISTS idx_canvas_reformat_pickable
    ON public.canvas_reformat_jobs(enqueued_at) WHERE status = 'pending';

COMMENT ON TABLE public.canvas_reformat_jobs IS
    'Async queue: regenerate canvas_nodes.content_json from an FS-edited content '
    'via the LLM formatter. Drained by worker_canvas_reformat.py (debounced). '
    'Internal plumbing — never rendered to FS, no sync trigger.';

COMMIT;
