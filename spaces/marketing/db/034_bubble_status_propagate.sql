-- ============================================================================
-- Schicht 7.1 — Auto-propagate broadcast_proposals status changes to linked bubbles
-- ============================================================================
-- Migration 033 added public.ideas.broadcast_proposal_id linking a bubble to
-- its downstream broadcast_proposal. The python-side handlers update
-- broadcast_proposals.status (approved/rejected/sent/failed) in 6 different
-- code paths. Easier to maintain: a single DB trigger that mirrors the
-- status to the linked bubble.
--
-- What it mirrors:
--   bp.status='approved'  -> bubble.status='approved'
--   bp.status='rejected'  -> bubble.status='rejected'
--   bp.status='sent'      -> bubble.status='sent'  (record_result handler also sets sent_external_id)
--   bp.status='failed'    -> bubble.status='send_failed'
--   bp.status='pending_approval' -> bubble.status='pending_approval'
--
-- What it does NOT mirror:
--   bubble.status='draft'/'idea' -> bp (the publish handler explicitly
--                                       links them; trigger is one-way bp->bubble)

BEGIN;

CREATE OR REPLACE FUNCTION marketing.propagate_broadcast_status_to_bubble()
RETURNS TRIGGER AS $$
DECLARE
    new_bubble_status text;
BEGIN
    -- only fire on status-change
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    new_bubble_status := CASE NEW.status
        WHEN 'approved'         THEN 'approved'
        WHEN 'rejected'         THEN 'rejected'
        WHEN 'sent'             THEN 'sent'
        WHEN 'failed'           THEN 'send_failed'
        WHEN 'pending_approval' THEN 'pending_approval'
        ELSE NULL
    END;

    IF new_bubble_status IS NULL THEN
        RETURN NEW;  -- unknown status, leave bubble alone
    END IF;

    UPDATE public.ideas
       SET status = new_bubble_status
     WHERE broadcast_proposal_id = NEW.id
       AND status IS DISTINCT FROM new_bubble_status;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_broadcast_propagate_to_bubble
    ON marketing.broadcast_proposals;

CREATE TRIGGER trg_broadcast_propagate_to_bubble
    AFTER UPDATE OF status ON marketing.broadcast_proposals
    FOR EACH ROW
    EXECUTE FUNCTION marketing.propagate_broadcast_status_to_bubble();

COMMENT ON FUNCTION marketing.propagate_broadcast_status_to_bubble() IS
    'Schicht 7.1: when a broadcast_proposals.status changes, mirror it to the '
    'linked public.ideas bubble. One-way (bp -> bubble). Bubble stays in sync '
    'without each python handler having to remember to update it.';

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:034',
    'bubble_status_propagation.trigger_added',
    'marketing.broadcast_proposals',
    jsonb_build_object(
        'trigger', 'trg_broadcast_propagate_to_bubble',
        'function', 'marketing.propagate_broadcast_status_to_bubble',
        'mirrored_states', jsonb_build_array(
            'pending_approval', 'approved', 'rejected', 'sent', 'failed'
        )
    )
);

COMMIT;
