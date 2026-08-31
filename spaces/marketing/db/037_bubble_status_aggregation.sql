-- ============================================================================
-- Schicht 8.0b — Aggregate N broadcast_proposals statuses -> 1 bubble status
-- ============================================================================
-- Plan: spaces/marketing/docs/2026-07-02-bubble-auto-dispatch-plan.md (Phase 1)
--
-- Migration 034 mirrored bp.status -> bubble.status 1:1 — correct while a
-- bubble had exactly ONE proposal. With per-channel fan-out (036: N bps per
-- bubble via bp.bubble_id) the mirror breaks: the last-updated bp would
-- clobber the bubble status. This migration replaces it with an aggregate.
--
-- Aggregation precedence (first match wins):
--   any pending_approval          -> 'pending_approval'  (work in flight)
--   any approved                  -> 'approved'          (sends pending)
--   sent AND (rejected OR failed) -> 'partially_sent'    (NEW value)
--   any sent                      -> 'sent'
--   any failed                    -> 'send_failed'
--   any rejected                  -> 'rejected'
--   any draft                     -> 'draft'
--   else                          -> leave bubble untouched
--
-- Single-bp bubbles keep 034 semantics exactly (verify: each single status
-- maps to the same value as before).
--
-- The old function marketing.propagate_broadcast_status_to_bubble() is left
-- in place (unused) for easy rollback: drop the new trigger, recreate
-- trg_broadcast_propagate_to_bubble against the old function.
--
-- Apply:
--   docker cp 037_bubble_status_aggregation.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/037_bubble_status_aggregation.sql

BEGIN;

CREATE OR REPLACE FUNCTION marketing.aggregate_bubble_status()
RETURNS TRIGGER AS $$
DECLARE
    target_bubble text;
    stats         text[];
    new_status    text;
BEGIN
    -- Only fire on real status changes (INSERT always counts)
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    -- Resolve bubble: prefer the explicit N:1 link (036), fall back to the
    -- legacy single-valued link for pre-036 rows.
    target_bubble := NEW.bubble_id;
    IF target_bubble IS NULL THEN
        SELECT id INTO target_bubble
          FROM public.ideas
         WHERE broadcast_proposal_id = NEW.id
         LIMIT 1;
    END IF;
    IF target_bubble IS NULL THEN
        RETURN NEW;  -- proposal not linked to any bubble
    END IF;

    -- Collect DISTINCT statuses of ALL proposals of this bubble
    -- (new-style link OR legacy link).
    SELECT array_agg(DISTINCT s.status) INTO stats FROM (
        SELECT bp.status
          FROM marketing.broadcast_proposals bp
         WHERE bp.bubble_id = target_bubble
        UNION
        SELECT bp2.status
          FROM marketing.broadcast_proposals bp2
          JOIN public.ideas i ON i.broadcast_proposal_id = bp2.id
         WHERE i.id = target_bubble
    ) s;

    new_status := CASE
        WHEN 'pending_approval' = ANY(stats) THEN 'pending_approval'
        WHEN 'approved'         = ANY(stats) THEN 'approved'
        WHEN 'sent' = ANY(stats)
             AND ('rejected' = ANY(stats) OR 'failed' = ANY(stats))
                                             THEN 'partially_sent'
        WHEN 'sent'             = ANY(stats) THEN 'sent'
        WHEN 'failed'           = ANY(stats) THEN 'send_failed'
        WHEN 'rejected'         = ANY(stats) THEN 'rejected'
        WHEN 'draft'            = ANY(stats) THEN 'draft'
        ELSE NULL
    END;

    IF new_status IS NULL THEN
        RETURN NEW;  -- unknown status mix, leave bubble alone
    END IF;

    UPDATE public.ideas
       SET status = new_status
     WHERE id = target_bubble
       AND status IS DISTINCT FROM new_status;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.aggregate_bubble_status() IS
    'Schicht 8.0b: aggregates ALL broadcast_proposals of a bubble into one '
    'bubble.status (precedence: pending_approval > approved > partially_sent '
    '> sent > send_failed > rejected > draft). Replaces the 1:1 mirror from '
    'migration 034 to support per-channel fan-out.';

-- Swap triggers: drop the 034 1:1 mirror, install the aggregate.
DROP TRIGGER IF EXISTS trg_broadcast_propagate_to_bubble
    ON marketing.broadcast_proposals;

DROP TRIGGER IF EXISTS trg_broadcast_aggregate_to_bubble
    ON marketing.broadcast_proposals;

CREATE TRIGGER trg_broadcast_aggregate_to_bubble
    AFTER INSERT OR UPDATE OF status ON marketing.broadcast_proposals
    FOR EACH ROW
    EXECUTE FUNCTION marketing.aggregate_bubble_status();

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:037',
    'bubble_status_aggregation.trigger_swapped',
    'marketing.broadcast_proposals',
    jsonb_build_object(
        'dropped_trigger', 'trg_broadcast_propagate_to_bubble',
        'created_trigger', 'trg_broadcast_aggregate_to_bubble',
        'function', 'marketing.aggregate_bubble_status',
        'new_bubble_status_value', 'partially_sent',
        'precedence', jsonb_build_array(
            'pending_approval', 'approved', 'partially_sent',
            'sent', 'send_failed', 'rejected', 'draft'
        )
    )
);

COMMIT;
