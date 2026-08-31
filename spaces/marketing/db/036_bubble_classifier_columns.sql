-- ============================================================================
-- Schicht 8.0 — Bubble-Auto-Dispatch: classifier columns + N:1 proposal link
-- ============================================================================
-- Plan: spaces/marketing/docs/2026-07-02-bubble-auto-dispatch-plan.md (Phase 1)
--
-- Two structural changes:
--
-- (a) public.ideas gets self-classification columns. The extended
--     bubble_evaluate capability writes category/color/channels[] with a
--     confidence score; the dispatcher fans out one broadcast_proposal per
--     channel. Below-threshold bubbles stay category=NULL (UI: white).
--
-- (b) marketing.broadcast_proposals gets bubble_id. Today the link lives
--     single-valued on public.ideas.broadcast_proposal_id (one bp per
--     bubble) — fan-out needs the inverse N:1 direction. The legacy column
--     stays for backward compat (points at the first/primary bp); existing
--     links are backfilled into the new column.
--
-- NOTE: public.ideas.status has NO check constraint (verified live
-- 2026-07-02), so the new aggregate value 'partially_sent' (migration 037)
-- needs no constraint change here.
--
-- Apply:
--   docker cp 036_bubble_classifier_columns.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/036_bubble_classifier_columns.sql

BEGIN;

-- ─── (a) classifier columns on public.ideas ────────────────────────────────

ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS color text;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS channels jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS auto_classified boolean NOT NULL DEFAULT false;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS classification_confidence numeric;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS classified_at timestamptz;

-- Postgres has no ADD CONSTRAINT IF NOT EXISTS — guard via catalog check.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ideas_category_known') THEN
        ALTER TABLE public.ideas ADD CONSTRAINT ideas_category_known CHECK (
            category IS NULL OR category IN
                ('marketing', 'crowdfunding', 'code_project', 'research', 'general')
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ideas_channels_is_array') THEN
        ALTER TABLE public.ideas ADD CONSTRAINT ideas_channels_is_array CHECK (
            jsonb_typeof(channels) = 'array'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ideas_classification_confidence_range') THEN
        ALTER TABLE public.ideas ADD CONSTRAINT ideas_classification_confidence_range CHECK (
            classification_confidence IS NULL
            OR (classification_confidence >= 0 AND classification_confidence <= 1)
        );
    END IF;
END $$;

COMMENT ON COLUMN public.ideas.category IS
    'Schicht 8.0: Zuständigkeits-Klasse (marketing|crowdfunding|code_project|research|general). '
    'NULL = unklassifiziert/general (UI: weiß). Gesetzt von bubble_evaluate-Classifier oder manuell.';
COMMENT ON COLUMN public.ideas.color IS
    'UI-Farbe abgeleitet aus category: marketing=#dc2626 crowdfunding=#ea580c '
    'code_project=#2563eb research=#9333ea general=#ffffff. Rein visuell.';
COMMENT ON COLUMN public.ideas.channels IS
    'JSONB-Array der Ziel-Kanäle, z.B. ["linkedin","x","email"]. Ersetzt das '
    'einwertige target_channel für den Fan-Out. Leeres Array = kein Dispatch.';
COMMENT ON COLUMN public.ideas.classification_confidence IS
    '0..1 — Classifier-Sicherheit. Unter Threshold (default 0.7) wird nicht '
    'auto-dispatched; Bubble bleibt weiß und wartet auf manuelle Zuordnung.';

CREATE INDEX IF NOT EXISTS idx_ideas_category
    ON public.ideas (category)
    WHERE category IS NOT NULL;

-- ─── (b) N:1 link on broadcast_proposals ───────────────────────────────────

ALTER TABLE marketing.broadcast_proposals
    ADD COLUMN IF NOT EXISTS bubble_id text REFERENCES public.ideas(id) ON DELETE SET NULL;

COMMENT ON COLUMN marketing.broadcast_proposals.bubble_id IS
    'Schicht 8.0: N:1-Link auf die Quell-Bubble (fan-out: 1 bp pro (bubble, channel)). '
    'Legacy-Link public.ideas.broadcast_proposal_id bleibt für Alt-Rows bestehen.';

-- Backfill existing 1:1 links into the new direction
UPDATE marketing.broadcast_proposals bp
   SET bubble_id = i.id
  FROM public.ideas i
 WHERE i.broadcast_proposal_id = bp.id
   AND bp.bubble_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_broadcast_proposals_bubble
    ON marketing.broadcast_proposals (bubble_id)
    WHERE bubble_id IS NOT NULL;

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:036',
    'bubble_classifier_columns.added',
    'public.ideas',
    jsonb_build_object(
        'ideas_columns', jsonb_build_array(
            'category', 'color', 'channels', 'auto_classified',
            'classification_confidence', 'classified_at'
        ),
        'broadcast_proposals_columns', jsonb_build_array('bubble_id'),
        'categories', jsonb_build_array(
            'marketing', 'crowdfunding', 'code_project', 'research', 'general'
        )
    )
);

COMMIT;
