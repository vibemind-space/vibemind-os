-- ============================================================================
-- Marketing-Ops: aggregate metrics views (read-only)
-- ============================================================================
-- Three SQL views the dashboard and /api/metrics consume.
--
-- All VIEWs (not materialised) -- the data volume is small enough that
-- on-demand aggregation is cheap, and a materialised view would need a
-- refresh schedule we don't have. If counts grow past ~1M sends, we'll
-- convert to CONCURRENTLY-refreshed materialised views.
--
-- Views NEVER reveal candidate emails or bodies -- only aggregated counts
-- plus the (existing) campaign / audience names. Safe to read from any
-- service_role caller and to expose via the read-only /api/metrics endpoint.

BEGIN;

-- ─── 1. Per-day send activity ──────────────────────────────────────────
-- One row per (date, campaign). Sums sent/bounced/replied so the UI can
-- render a sparkline. NULL date_bucket = rows that never had sent_at set
-- (e.g. queued-only).
CREATE OR REPLACE VIEW marketing.v_send_activity_daily AS
SELECT
    date_trunc('day', cs.sent_at)::date     AS date_bucket,
    cs.campaign_id,
    c.name                                  AS campaign_name,
    COUNT(*)                                AS sends,
    COUNT(*) FILTER (WHERE cs.bounced_at IS NOT NULL)    AS bounces,
    COUNT(*) FILTER (WHERE cs.replied_at IS NOT NULL)    AS replies,
    COUNT(*) FILTER (WHERE cs.delivered_at IS NOT NULL)  AS delivered
FROM marketing.campaign_sends cs
LEFT JOIN marketing.campaigns c ON c.id = cs.campaign_id
WHERE cs.sent_at IS NOT NULL
GROUP BY date_bucket, cs.campaign_id, c.name;

COMMENT ON VIEW marketing.v_send_activity_daily IS
    'Per-day x per-campaign send activity. Read-only; populates dashboard sparklines.';

GRANT SELECT ON marketing.v_send_activity_daily TO service_role;


-- ─── 2. Per-campaign aggregate ─────────────────────────────────────────
-- One row per campaign with reply-rate, bounce-rate, delivery-rate.
CREATE OR REPLACE VIEW marketing.v_campaign_metrics AS
SELECT
    c.id                                                 AS campaign_id,
    c.name                                               AS campaign_name,
    c.status                                             AS campaign_status,
    c.audience_id,
    COUNT(cs.id)                                         AS sends_total,
    COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL)   AS sends_sent,
    COUNT(cs.id) FILTER (WHERE cs.delivered_at IS NOT NULL) AS sends_delivered,
    COUNT(cs.id) FILTER (WHERE cs.bounced_at IS NOT NULL)   AS sends_bounced,
    COUNT(cs.id) FILTER (WHERE cs.replied_at IS NOT NULL)   AS sends_replied,
    -- Rates safe-division (avoid /0)
    CASE WHEN COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL) > 0
         THEN ROUND(
             100.0 * COUNT(cs.id) FILTER (WHERE cs.bounced_at IS NOT NULL)
                   / COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL),
             2)
         ELSE NULL
    END                                                  AS bounce_rate_pct,
    CASE WHEN COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL) > 0
         THEN ROUND(
             100.0 * COUNT(cs.id) FILTER (WHERE cs.replied_at IS NOT NULL)
                   / COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL),
             2)
         ELSE NULL
    END                                                  AS reply_rate_pct,
    MAX(cs.sent_at)                                      AS last_send_at
FROM marketing.campaigns c
LEFT JOIN marketing.campaign_sends cs ON cs.campaign_id = c.id
GROUP BY c.id, c.name, c.status, c.audience_id;

COMMENT ON VIEW marketing.v_campaign_metrics IS
    'Aggregate metrics per campaign. Read-only.';

GRANT SELECT ON marketing.v_campaign_metrics TO service_role;


-- ─── 3. Top-level stack metrics ────────────────────────────────────────
-- Single-row snapshot for the dashboard tile. Most counts already
-- available via the get_stats tool, but this view adds the rates.
CREATE OR REPLACE VIEW marketing.v_stack_metrics AS
SELECT
    (SELECT COUNT(*) FROM marketing.accounts)                       AS accounts_total,
    (SELECT COUNT(*) FROM marketing.emails)                         AS emails_total,
    (SELECT COUNT(*) FROM marketing.emails WHERE smtp_valid = 1)    AS emails_verified,
    (SELECT COUNT(*) FROM marketing.emails WHERE consent_given_at IS NOT NULL)
                                                                    AS emails_with_consent,
    (SELECT COUNT(*) FROM marketing.emails WHERE investor_already_sent = true)
                                                                    AS emails_investor_locked,
    (SELECT COUNT(*) FROM marketing.emails WHERE unsubscribed_at IS NOT NULL)
                                                                    AS emails_unsubscribed,
    (SELECT COUNT(*) FROM marketing.audiences)                      AS audiences_total,
    (SELECT COUNT(*) FROM marketing.audience_members)               AS audience_members_total,
    (SELECT COUNT(*) FROM marketing.campaigns)                      AS campaigns_total,
    (SELECT COUNT(*) FROM marketing.campaigns WHERE status = 'sent') AS campaigns_sent,
    (SELECT COUNT(*) FROM marketing.campaign_sends)                 AS sends_total,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE sent_at IS NOT NULL)
                                                                    AS sends_sent,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE delivered_at IS NOT NULL)
                                                                    AS sends_delivered,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE bounced_at IS NOT NULL)
                                                                    AS sends_bounced,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE replied_at IS NOT NULL)
                                                                    AS sends_replied,
    (SELECT COUNT(*) FROM marketing.audience_proposals
        WHERE status = 'pending_review')                            AS proposals_pending,
    (SELECT COUNT(*) FROM marketing.audience_proposals
        WHERE status = 'approved')                                  AS proposals_approved,
    (SELECT COUNT(*) FROM marketing.audience_proposals
        WHERE status = 'rejected')                                  AS proposals_rejected,
    (SELECT COUNT(*) FROM marketing.inbound_messages
        WHERE received_at > now() - interval '7 days')              AS inbound_7d,
    (SELECT COUNT(*) FROM marketing.inbound_messages
        WHERE is_bounce = true)                                     AS inbound_bounces_total,
    -- Rates (NULL-safe)
    CASE WHEN (SELECT COUNT(*) FROM marketing.campaign_sends WHERE sent_at IS NOT NULL) > 0
         THEN ROUND(
             100.0 *
             (SELECT COUNT(*) FROM marketing.campaign_sends WHERE replied_at IS NOT NULL)
             /
             (SELECT COUNT(*) FROM marketing.campaign_sends WHERE sent_at IS NOT NULL),
             2)
         ELSE NULL
    END                                                             AS reply_rate_pct,
    CASE WHEN (SELECT COUNT(*) FROM marketing.campaign_sends WHERE sent_at IS NOT NULL) > 0
         THEN ROUND(
             100.0 *
             (SELECT COUNT(*) FROM marketing.campaign_sends WHERE bounced_at IS NOT NULL)
             /
             (SELECT COUNT(*) FROM marketing.campaign_sends WHERE sent_at IS NOT NULL),
             2)
         ELSE NULL
    END                                                             AS bounce_rate_pct;

COMMENT ON VIEW marketing.v_stack_metrics IS
    'Single-row dashboard tile. Read-only; aggregated counts only, no PII.';

GRANT SELECT ON marketing.v_stack_metrics TO service_role;


-- ─── Audit ─────────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:013',
    'schema.add_views',
    'marketing',
    jsonb_build_object(
        'views_added', jsonb_build_array(
            'marketing.v_send_activity_daily',
            'marketing.v_campaign_metrics',
            'marketing.v_stack_metrics'
        ),
        'send_impact', 'none -- read-only views over existing tables'
    )
);

COMMIT;
