-- ============================================================================
-- Verification for migrations 036 + 037 — runs inside a TRANSACTION + ROLLBACK
-- ============================================================================
-- Creates a test bubble + 3 broadcast_proposals (fan-out shape), walks them
-- through the approval lifecycle and asserts the aggregated bubble.status
-- after each step. Leaves ZERO residue (ROLLBACK at the end).
--
-- Run:
--   docker cp verify_036_037.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/verify_036_037.sql
--
-- Expected output: PASS 0..8 notices, then "ALL 8 CHECKS PASSED", then ROLLBACK.

BEGIN;

-- temp assertion helper (lives in pg_temp, vanishes with the session)
CREATE FUNCTION pg_temp.assert_bubble(step text, b text, expected text)
RETURNS void AS $$
DECLARE
    st text;
BEGIN
    SELECT status INTO st FROM public.ideas WHERE id = b;
    IF st IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'FAIL %: bubble.status=% expected=%', step, st, expected;
    END IF;
    RAISE NOTICE 'PASS %: bubble.status=%', step, st;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    b_id text := 'verify-agg-bubble-036037';
    ch   text;
    bp1  uuid;
    bp2  uuid;
    bp3  uuid;
BEGIN
    -- pick an existing channel (FK to marketing.channel_config)
    SELECT channel INTO ch FROM marketing.channel_config LIMIT 1;
    IF ch IS NULL THEN
        RAISE EXCEPTION 'FAIL setup: no rows in marketing.channel_config';
    END IF;
    RAISE NOTICE 'setup: using channel=%', ch;

    -- (0) classifier columns exist + accept values
    INSERT INTO public.ideas (id, title, kind, status,
                              category, color, channels,
                              auto_classified, classification_confidence,
                              classified_at)
    VALUES (b_id, 'Verify aggregation bubble', 'post_draft', 'draft',
            'marketing', '#dc2626', '["linkedin","x","email"]'::jsonb,
            true, 0.87, now());
    RAISE NOTICE 'PASS 0: classifier columns accept category/color/channels/confidence';

    -- (1) fan-out: 3 proposals via NEW bubble_id link, all draft
    INSERT INTO marketing.broadcast_proposals (channel, status, draft_body_text, created_by, bubble_id)
    VALUES (ch, 'draft', 'verify body 1', 'verify-script', b_id) RETURNING id INTO bp1;
    INSERT INTO marketing.broadcast_proposals (channel, status, draft_body_text, created_by, bubble_id)
    VALUES (ch, 'draft', 'verify body 2', 'verify-script', b_id) RETURNING id INTO bp2;
    INSERT INTO marketing.broadcast_proposals (channel, status, draft_body_text, created_by, bubble_id)
    VALUES (ch, 'draft', 'verify body 3', 'verify-script', b_id) RETURNING id INTO bp3;
    PERFORM pg_temp.assert_bubble('1 (3x draft)', b_id, 'draft');

    -- (2) all pending_approval
    UPDATE marketing.broadcast_proposals
       SET status = 'pending_approval',
           approval_requested_at = now(),
           approval_token_hash = 'verify-hash'
     WHERE id IN (bp1, bp2, bp3);
    PERFORM pg_temp.assert_bubble('2 (3x pending)', b_id, 'pending_approval');

    -- (3) one approved, two still pending -> pending wins
    UPDATE marketing.broadcast_proposals
       SET status = 'approved', approved_at = now(), approved_by = 'verify',
           approval_token_hash = NULL
     WHERE id = bp1;
    PERFORM pg_temp.assert_bubble('3 (approved+2 pending)', b_id, 'pending_approval');

    -- (4) second rejected, third still pending -> pending still wins
    UPDATE marketing.broadcast_proposals
       SET status = 'rejected', rejected_at = now(), rejected_by = 'verify',
           approval_token_hash = NULL
     WHERE id = bp2;
    PERFORM pg_temp.assert_bubble('4 (approved+rejected+pending)', b_id, 'pending_approval');

    -- (5) third approved -> no pending left, approved wins
    UPDATE marketing.broadcast_proposals
       SET status = 'approved', approved_at = now(), approved_by = 'verify',
           approval_token_hash = NULL
     WHERE id = bp3;
    PERFORM pg_temp.assert_bubble('5 (2 approved+rejected)', b_id, 'approved');

    -- (6) both approved ones sent -> sent+rejected mix = partially_sent (NEW)
    UPDATE marketing.broadcast_proposals
       SET status = 'sent', sent_at = now()
     WHERE id IN (bp1, bp3);
    PERFORM pg_temp.assert_bubble('6 (2 sent+1 rejected)', b_id, 'partially_sent');

    -- (7) single-bp bubble keeps 034 semantics: rejected -> rejected
    DELETE FROM marketing.broadcast_proposals WHERE id IN (bp1, bp3);
    UPDATE marketing.broadcast_proposals SET status = 'draft' WHERE id = bp2;
    UPDATE marketing.broadcast_proposals
       SET status = 'rejected', rejected_at = now(), rejected_by = 'verify'
     WHERE id = bp2;
    PERFORM pg_temp.assert_bubble('7 (single bp rejected)', b_id, 'rejected');

    -- (8) legacy-link fallback: bubble linked via ideas.broadcast_proposal_id
    --     (bp WITHOUT bubble_id) still aggregates
    UPDATE marketing.broadcast_proposals SET bubble_id = NULL WHERE id = bp2;
    UPDATE public.ideas SET broadcast_proposal_id = bp2 WHERE id = b_id;
    UPDATE marketing.broadcast_proposals
       SET status = 'sent', sent_at = now()
     WHERE id = bp2;
    PERFORM pg_temp.assert_bubble('8 (legacy link, sent)', b_id, 'sent');

    RAISE NOTICE 'ALL 8 CHECKS PASSED — rolling back test data';
END $$;

ROLLBACK;
