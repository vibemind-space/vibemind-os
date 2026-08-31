"""Centralised SQL strings for the sync system.

A single account-render is one big query with JSON aggregations — one
round-trip per markdown file, even with 6 join sources. The query returns
exactly the shape the frontmatter renderer expects.

If a tested SQL field changes here, snapshot tests must be re-blessed.
"""
from __future__ import annotations

# ─── full single-account fetch ─────────────────────────────────────────────
# Returns ONE row with all data needed to render the markdown file.
ACCOUNT_RENDER_QUERY = """
SELECT
    a.sync_id::text AS sync_id,
    a.handle,
    COALESCE(NULLIF(a.display_name, ''), '') AS display_name,
    COALESCE(NULLIF(a.niche, ''), '') AS niche,
    COALESCE(NULLIF(a.source, ''), '') AS source,
    a.followers,
    a.bio,
    a.created_at,
    a.last_synced_at,

    -- all emails for this account, sorted by confidence DESC
    (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'email', e.email,
            'confidence', e.confidence,
            'mx_valid', e.mx_valid,
            'smtp_valid', e.smtp_valid,
            'domain', e.domain,
            'country', e.country,
            'catch_all', e.catch_all,
            'consent_given_at', e.consent_given_at,
            'consent_source', e.consent_source,
            'unsubscribed_at', e.unsubscribed_at,
            'bounce_count', e.bounce_count,
            'last_engagement_at', e.last_engagement_at,
            'investor_already_sent', e.investor_already_sent
        ) ORDER BY e.confidence DESC, e.created_at ASC), '[]'::jsonb)
        FROM marketing.emails e
        WHERE e.handle = a.handle
    ) AS emails,

    -- primary email = highest confidence
    (SELECT email FROM marketing.emails e
     WHERE e.handle = a.handle
     ORDER BY e.confidence DESC, e.created_at ASC LIMIT 1) AS primary_email,

    -- distinct tags across all emails of this account
    (
        SELECT COALESCE(jsonb_agg(DISTINCT t.name ORDER BY t.name), '[]'::jsonb)
        FROM marketing.email_tags et
        JOIN marketing.tags t ON t.id = et.tag_id
        WHERE et.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS tags,

    -- audience memberships
    (
        SELECT COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
            'audience_id', aud.id,
            'audience_name', aud.name,
            'added_at', am.added_at
        ) ORDER BY jsonb_build_object('audience_id', aud.id, 'audience_name', aud.name, 'added_at', am.added_at)), '[]'::jsonb)
        FROM marketing.audience_members am
        JOIN marketing.audiences aud ON aud.id = am.audience_id
        WHERE am.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS audience_memberships,

    -- send roll-up
    (SELECT COUNT(*) FROM marketing.campaign_sends cs
     WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS send_history_count,
    (SELECT MAX(sent_at) FROM marketing.campaign_sends cs
     WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS last_send_at,
    (SELECT MAX(opened_at) FROM marketing.campaign_sends cs
     WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS last_open_at,
    (SELECT MAX(clicked_at) FROM marketing.campaign_sends cs
     WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS last_click_at,
    (SELECT MAX(replied_at) FROM marketing.campaign_sends cs
     WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS last_reply_at,

    -- inbound roll-up
    (SELECT COUNT(*) FROM marketing.inbound_messages im
     WHERE im.from_email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS inbound_count,
    (SELECT MAX(received_at) FROM marketing.inbound_messages im
     WHERE im.from_email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
    ) AS last_inbound_at,

    -- recent campaign_sends (LIMIT 20) for body section
    (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'campaign_id', cs.campaign_id,
            'campaign_name', c.name,
            'email', cs.email,
            'sent_at', cs.sent_at,
            'opened_at', cs.opened_at,
            'clicked_at', cs.clicked_at,
            'replied_at', cs.replied_at,
            'bounced_at', cs.bounced_at
        ) ORDER BY cs.sent_at DESC) FILTER (WHERE rn <= 20), '[]'::jsonb)
        FROM (
            SELECT cs.*, ROW_NUMBER() OVER (ORDER BY cs.sent_at DESC) AS rn,
                   c.name
            FROM marketing.campaign_sends cs
            LEFT JOIN marketing.campaigns c ON c.id = cs.campaign_id
            WHERE cs.email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
        ) cs(id, campaign_id, email, queued_at, sent_at, delivered_at, opened_at, clicked_at,
             replied_at, bounced_at, bounce_reason, unsubscribed_at, open_count, click_count,
             rn, name)
        LEFT JOIN marketing.campaigns c ON c.id = cs.campaign_id
    ) AS recent_sends,

    -- recent inbound (LIMIT 20)
    (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'received_at', im.received_at,
            'from_email', im.from_email,
            'from_name', im.from_name,
            'subject', im.subject,
            'is_bounce', im.is_bounce,
            'is_autoreply', im.is_autoreply
        ) ORDER BY im.received_at DESC), '[]'::jsonb)
        FROM (
            SELECT im.*, ROW_NUMBER() OVER (ORDER BY im.received_at DESC) AS rn
            FROM marketing.inbound_messages im
            WHERE im.from_email IN (SELECT email FROM marketing.emails WHERE handle = a.handle)
        ) im
        WHERE im.rn <= 20
    ) AS recent_inbound,

    -- strategies that generated any email of this account
    (
        SELECT COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
            'id', s.id,
            'format_pattern', s.format_pattern,
            'domain', s.domain,
            'fitness', s.fitness,
            'success_count', s.success_count
        )), '[]'::jsonb)
        FROM marketing.strategies s
        WHERE s.id IN (SELECT strategy_id FROM marketing.emails WHERE handle = a.handle)
          AND s.id <> ''
    ) AS strategies

FROM marketing.accounts a
WHERE a.handle = %(handle)s
"""


# ─── bulk list for full re-render ──────────────────────────────────────────
LIST_ALL_HANDLES_QUERY = """
SELECT handle, sync_id::text, last_synced_at
FROM marketing.accounts
ORDER BY handle
"""

# Like LIST_ALL but only handles whose data might have changed since
# last_synced_at — used for `--only-changed` full re-render.
LIST_STALE_HANDLES_QUERY = """
WITH max_change AS (
    SELECT a.handle,
           GREATEST(
               COALESCE(MAX(a.created_at), '1970-01-01'::timestamptz),
               COALESCE(MAX(e.created_at), '1970-01-01'::timestamptz),
               COALESCE(MAX(am.added_at), '1970-01-01'::timestamptz),
               COALESCE(MAX(cs.queued_at), '1970-01-01'::timestamptz),
               COALESCE(MAX(im.received_at), '1970-01-01'::timestamptz)
           ) AS latest
    FROM marketing.accounts a
    LEFT JOIN marketing.emails e ON e.handle = a.handle
    LEFT JOIN marketing.audience_members am ON am.email = e.email
    LEFT JOIN marketing.campaign_sends cs ON cs.email = e.email
    LEFT JOIN marketing.inbound_messages im ON im.from_email = e.email
    GROUP BY a.handle
)
SELECT a.handle, a.sync_id::text, a.last_synced_at, m.latest
FROM marketing.accounts a
JOIN max_change m ON m.handle = a.handle
WHERE a.last_synced_at IS NULL OR a.last_synced_at < m.latest
ORDER BY a.handle
"""
