-- ============================================================================
-- Marketing-Ops: engagement + campaign-performance views (Schicht 5.4)
-- ============================================================================
-- Two views:
--   1. marketing.v_recipient_engagement
--        Per-recipient aggregated metrics: how many campaigns received,
--        opened, clicked, replied. Plus a weighted score that captures
--        "how engaged is this person."
--   2. marketing.v_campaign_performance
--        Per-campaign aggregated metrics: deliveries, bounces, unique
--        opens, total opens, unique clicks, total clicks, replies.
--        Lets the dashboard show open-rate and CTR per campaign.
--
-- The score formula in v_recipient_engagement is intentionally simple
-- and explainable: events have integer weights, and we just sum them.
--    open       = +1
--    click      = +3  (stronger signal of intent)
--    reply      = +5  (strongest possible engagement)
--    unsubscribed = -10 penalty (sticky -- not undone)
--
-- These views are READ-ONLY. They never write. Refreshing is implicit
-- on SELECT (no materialization). For volume > 100k sends, Schicht 6
-- introduces materialized views with a refresh schedule.
--
-- Apply:
--   docker cp 023_engagement_views.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/023_engagement_views.sql

BEGIN;

-- ─── v_recipient_engagement ───────────────────────────────────────────
CREATE OR REPLACE VIEW marketing.v_recipient_engagement AS
WITH per_recipient AS (
    SELECT
        e.email,
        e.unsubscribed_at,
        -- "hard-bounced" proxy: smtp_valid=0 means an explicit fail,
        -- bounce_count>0 means at least one delivery attempt bounced.
        (e.smtp_valid = 0 OR e.bounce_count > 0) AS is_bounced,
        -- counts
        (SELECT COUNT(*) FROM marketing.campaign_sends cs
          WHERE cs.email = e.email AND cs.sent_at IS NOT NULL) AS sends_count,
        (SELECT COUNT(DISTINCT cs.campaign_id) FROM marketing.campaign_sends cs
          WHERE cs.email = e.email AND cs.sent_at IS NOT NULL) AS campaigns_received,
        (SELECT COUNT(DISTINCT eo.campaign_id) FROM marketing.email_opens eo
          WHERE eo.email = e.email) AS campaigns_opened,
        (SELECT COUNT(*) FROM marketing.email_opens eo
          WHERE eo.email = e.email) AS total_opens,
        (SELECT COUNT(DISTINCT ec.campaign_id) FROM marketing.email_clicks ec
          WHERE ec.email = e.email) AS campaigns_clicked,
        (SELECT COUNT(*) FROM marketing.email_clicks ec
          WHERE ec.email = e.email) AS total_clicks,
        (SELECT COUNT(*) FROM marketing.campaign_sends cs
          WHERE cs.email = e.email AND cs.replied_at IS NOT NULL) AS replies_count,
        -- last activity (whichever happened latest)
        GREATEST(
            (SELECT MAX(opened_at)  FROM marketing.email_opens   WHERE email = e.email),
            (SELECT MAX(clicked_at) FROM marketing.email_clicks  WHERE email = e.email),
            (SELECT MAX(replied_at) FROM marketing.campaign_sends WHERE email = e.email)
        ) AS last_activity_at
    FROM marketing.emails e
)
SELECT
    email,
    sends_count,
    campaigns_received,
    campaigns_opened,
    total_opens,
    campaigns_clicked,
    total_clicks,
    replies_count,
    CASE WHEN unsubscribed_at IS NOT NULL THEN true ELSE false END AS unsubscribed,
    is_bounced AS hard_bounced,
    last_activity_at,
    -- Engagement score: weighted sum
    (total_opens * 1)
      + (total_clicks * 3)
      + (replies_count * 5)
      + CASE WHEN unsubscribed_at IS NOT NULL THEN -10 ELSE 0 END
      + CASE WHEN is_bounced                  THEN -5  ELSE 0 END
        AS engagement_score
FROM per_recipient;

COMMENT ON VIEW marketing.v_recipient_engagement IS
    'Per-recipient lifetime engagement: send/open/click/reply counts + weighted '
    'score. Lower bound is whatever unsub/bounce penalty applies; upper bound '
    'is unlimited. Use ORDER BY engagement_score DESC for "best leads."';


-- ─── v_campaign_performance ──────────────────────────────────────────
CREATE OR REPLACE VIEW marketing.v_campaign_performance AS
SELECT
    c.id                        AS campaign_id,
    c.name                      AS campaign_name,
    c.channel                   AS channel,
    c.status                    AS status,
    c.created_at,
    c.sent_at,
    -- email-channel counts
    (SELECT COUNT(*) FROM marketing.campaign_sends cs
      WHERE cs.campaign_id = c.id AND cs.sent_at IS NOT NULL) AS email_delivered,
    (SELECT COUNT(*) FROM marketing.campaign_sends cs
      WHERE cs.campaign_id = c.id AND cs.bounced_at IS NOT NULL) AS email_bounced,
    (SELECT COUNT(*) FROM marketing.campaign_sends cs
      WHERE cs.campaign_id = c.id AND cs.replied_at IS NOT NULL) AS email_replies,
    -- open metrics
    (SELECT COUNT(DISTINCT eo.email) FROM marketing.email_opens eo
      WHERE eo.campaign_id = c.id) AS unique_opens,
    (SELECT COUNT(*) FROM marketing.email_opens eo
      WHERE eo.campaign_id = c.id) AS total_opens,
    -- click metrics
    (SELECT COUNT(DISTINCT ec.email) FROM marketing.email_clicks ec
      WHERE ec.campaign_id = c.id) AS unique_clicks,
    (SELECT COUNT(*) FROM marketing.email_clicks ec
      WHERE ec.campaign_id = c.id) AS total_clicks
FROM marketing.campaigns c;

COMMENT ON VIEW marketing.v_campaign_performance IS
    'Per-campaign aggregated metrics. Use unique_opens/email_delivered for '
    'open-rate, unique_clicks/unique_opens for CTR. Email-only today; '
    'multi-channel aggregation (telegram_sent, openfang_sent) already in '
    'v_campaign_metrics — that view + this view together describe a campaign.';


INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:023',
    'engagement_views.created',
    'marketing.v_recipient_engagement',
    jsonb_build_object(
        'views', jsonb_build_array(
            'marketing.v_recipient_engagement',
            'marketing.v_campaign_performance'
        ),
        'note',
        'Read-only views. No materialization yet. For >100k sends, Schicht 6 '
        'adds REFRESH MATERIALIZED VIEW + cron.'
    )
);

COMMIT;
