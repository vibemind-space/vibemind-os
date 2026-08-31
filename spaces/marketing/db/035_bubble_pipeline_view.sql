-- ============================================================================
-- Schicht 7.2 — Read-only view that joins bubble + proposal + approval state
-- ============================================================================
-- Pain-point from spaces/marketing/docs/COCKPIT_FRICTION_LOG.md (#2):
-- "Status-monitoring requires SQL. Multiple separate SELECTs across
--  public.ideas + marketing.broadcast_proposals to answer 'where is this
--  post in the pipeline'."
--
-- This view collapses the join into a single read so any caller (cockpit,
-- CLI, dashboards) can ask "what's the pipeline state of every post-draft
-- bubble" in one query.
--
-- Strictly read-only and computed-on-demand (low volume; <10k bubbles total).
-- No PII: titles + status + score only. Body stays in public.ideas.description
-- for callers who explicitly ask for it.

BEGIN;

CREATE OR REPLACE VIEW marketing.v_bubble_pipeline AS
SELECT
    i.id                                   AS bubble_id,
    i.title                                AS bubble_title,
    i.target_channel                       AS channel,
    i.status                               AS bubble_status,
    i.kind                                 AS bubble_kind,
    i.mirofish_score,
    i.mirofish_report_id,
    i.mirofish_last_run_at,
    i.broadcast_proposal_id                AS proposal_id,
    bp.status                              AS proposal_status,
    bp.openfang_approval_id,
    bp.approval_requested_at,
    bp.approved_at,
    bp.approved_by,
    bp.rejected_at,
    bp.rejected_by,
    bp.rejection_reason,
    bp.sent_at,
    bp.sent_external_id                    AS proposal_sent_external_id,
    i.sent_external_id                     AS bubble_sent_external_id,
    -- single-string pipeline stage derived from the combined state
    CASE
        WHEN i.status = 'draft' AND i.mirofish_report_id IS NULL
             THEN 'draft'
        WHEN i.mirofish_report_id IS NOT NULL AND i.broadcast_proposal_id IS NULL
             THEN 'predicted'
        WHEN bp.status = 'pending_approval'
             THEN 'awaiting_approval'
        WHEN bp.status = 'approved' AND bp.sent_at IS NULL
             THEN 'approved'
        WHEN bp.status = 'sent'
             THEN 'sent'
        WHEN bp.status = 'rejected'
             THEN 'rejected'
        WHEN bp.status = 'failed'
             THEN 'send_failed'
        ELSE COALESCE(bp.status, i.status)
    END                                    AS pipeline_stage,
    i.created_at                           AS bubble_created_at,
    i.updated_at                           AS bubble_updated_at,
    bp.created_at                          AS proposal_created_at,
    bp.updated_at                          AS proposal_updated_at
FROM public.ideas AS i
LEFT JOIN marketing.broadcast_proposals AS bp
       ON bp.id = i.broadcast_proposal_id
WHERE i.kind = 'post_draft';

COMMENT ON VIEW marketing.v_bubble_pipeline IS
    'Schicht 7.2: one row per post_draft bubble with its joined '
    'broadcast_proposal + derived pipeline_stage. Replaces three separate '
    'SELECTs for status-check (cockpit friction-log #2).';

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:035',
    'bubble_pipeline_view.created',
    'marketing.v_bubble_pipeline',
    jsonb_build_object(
        'view', 'marketing.v_bubble_pipeline',
        'stages', jsonb_build_array(
            'draft', 'predicted', 'awaiting_approval',
            'approved', 'sent', 'rejected', 'send_failed'
        )
    )
);

COMMIT;
