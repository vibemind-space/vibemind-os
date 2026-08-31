-- ============================================================================
-- Schicht 7.1 — Marketing-Posts as first-class Bubbles
-- ============================================================================
-- Felix's idea: Marketing posts shouldn't be ephemeral broadcast_proposals.
-- They should be Bubbles in public.ideas — persistent, embeddable, evaluable
-- via Mirofish, iterable in Rowboat (.md-vault sync existing), routable to
-- Brain. broadcast_proposals becomes the SEND-projection of a Bubble, not
-- the source of truth.
--
-- Flow:
--   Felix creates Bubble (kind='post_draft', target_channel='linkedin')
--     -> bubble→rowboat bidi-sync gives Markdown vault file
--     -> Felix clicks "Evaluate" -> mirofish predict_post_reception()
--        writes mirofish_report_id + mirofish_score back
--     -> Felix clicks "Post" -> creates marketing.broadcast_proposal,
--        linked back via broadcast_proposal_id
--     -> OpenFang approval-UI -> bridge -> n8n -> LinkedIn
--     -> on success: sent_external_id propagated back to Bubble
--
-- Out of scope here:
--   - UI buttons (Phase 2)
--   - Brain auto-trigger (Phase 3)
--   - Video-Space asset binding (Phase 3)
--
-- Apply:
--   docker cp 033_bubble_post_drafts.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/033_bubble_post_drafts.sql

BEGIN;

-- ── Columns ──────────────────────────────────────────────────────

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'idea';

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS target_channel text;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS mirofish_report_id text;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS mirofish_score integer;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS mirofish_last_run_at timestamptz;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS broadcast_proposal_id uuid;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS sent_external_id text;

-- ── Comments ──────────────────────────────────────────────────────

COMMENT ON COLUMN public.ideas.kind IS
    'Taxonomy: ''idea'' (default, free-form), ''post_draft'' (marketing post candidate). '
    'Used to filter the Bubble-UI tabs.';

COMMENT ON COLUMN public.ideas.target_channel IS
    'For kind=post_draft: ''linkedin'' | ''x'' | ''reddit'' | ''discord'' | ''mastodon''. '
    'NULL for kind=idea. Determines which Mirofish-simulation platform + which '
    'broadcast_proposal channel.';

COMMENT ON COLUMN public.ideas.mirofish_report_id IS
    'ID of the last predict_post_reception() run. Used to fetch full report + '
    'interview personas. Cleared on bubble.description edit (re-eval needed).';

COMMENT ON COLUMN public.ideas.mirofish_score IS
    'Compact summary score 0-100 from mirofish_report. UI badge. NULL if not yet evaluated.';

COMMENT ON COLUMN public.ideas.mirofish_last_run_at IS
    'When predict_post_reception() last ran for this bubble. Helps detect stale evals '
    'after bubble.description edits.';

COMMENT ON COLUMN public.ideas.broadcast_proposal_id IS
    'After Felix clicks "Post", a row is created in marketing.broadcast_proposals and '
    'linked here. From here all downstream events (approval, send, result) reference '
    'this proposal_id.';

COMMENT ON COLUMN public.ideas.sent_external_id IS
    'Platform-side external ID after successful send (e.g. urn:li:share:7472907761669001217). '
    'Propagated back from broadcast_proposals.sent_external_id by broadcast_to_bubble worker.';

-- ── Constraints ──────────────────────────────────────────────────

-- kind ∈ {idea, post_draft, ...future}. We don't enum-lock yet to stay flexible.

-- target_channel only valid for post_draft
ALTER TABLE public.ideas
    DROP CONSTRAINT IF EXISTS ideas_target_channel_requires_post_draft;
ALTER TABLE public.ideas
    ADD CONSTRAINT ideas_target_channel_requires_post_draft
    CHECK (
        target_channel IS NULL
        OR kind = 'post_draft'
    );

-- known channels (extend as we add pilots)
ALTER TABLE public.ideas
    DROP CONSTRAINT IF EXISTS ideas_target_channel_known;
ALTER TABLE public.ideas
    ADD CONSTRAINT ideas_target_channel_known
    CHECK (
        target_channel IS NULL
        OR target_channel IN ('linkedin', 'x', 'reddit', 'discord', 'mastodon', 'telegram')
    );

-- mirofish_score sane bounds
ALTER TABLE public.ideas
    DROP CONSTRAINT IF EXISTS ideas_mirofish_score_range;
ALTER TABLE public.ideas
    ADD CONSTRAINT ideas_mirofish_score_range
    CHECK (mirofish_score IS NULL OR mirofish_score BETWEEN 0 AND 100);

-- ── Indexes ──────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ideas_post_drafts
    ON public.ideas (kind, target_channel, status)
    WHERE kind = 'post_draft';

CREATE INDEX IF NOT EXISTS idx_ideas_broadcast_link
    ON public.ideas (broadcast_proposal_id)
    WHERE broadcast_proposal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ideas_pending_eval
    ON public.ideas (kind, mirofish_last_run_at)
    WHERE kind = 'post_draft' AND mirofish_report_id IS NULL;

COMMIT;
