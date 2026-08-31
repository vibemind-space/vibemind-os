-- ============================================================================
-- Marketing-Ops: click-tracking (Schicht 5.2)
-- ============================================================================
-- Brevo-equivalent recipient click-tracking via link rewrite.
--
-- Flow:
--   1. _send_paranoid renders template with tracking_enabled=true.
--   2. tools/tracking.rewrite_links replaces every <a href="X"> with
--      <a href="{MARKETING_TRACKING_BASE_URL}/t/c/{token}?u={X}">.
--   3. Token's HMAC binds the URL hash -> tampering with `u=` rejects.
--   4. /t/c/{token} endpoint:
--        - HMAC-verify token AND check the `u=` param hashes to the
--          same value the token was signed over
--        - INSERTs row in marketing.email_clicks
--        - 302 Location: <original URL>
--        - emits webhook event 'click'
--   5. webhook_delivery worker fans 'click' events to subscriptions.
--
-- Multiple clicks by the same recipient = multiple rows.
--
-- Security:
--   The URL hash is BAKED INTO the HMAC. If an attacker swaps `u=` to
--   phishing-site.example, the token does not verify, the route returns
--   404. So our tracking domain is NOT a generic open-redirect.
--
-- Apply:
--   docker cp 022_email_clicks.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/022_email_clicks.sql

BEGIN;

CREATE TABLE IF NOT EXISTS marketing.email_clicks (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     uuid        NOT NULL REFERENCES marketing.campaigns(id) ON DELETE CASCADE,
    email           citext      NOT NULL,
    clicked_at      timestamptz NOT NULL DEFAULT now(),
    url             text        NOT NULL,
    user_agent      text,
    ip              inet,
    msgid_core      text
);

CREATE INDEX IF NOT EXISTS idx_email_clicks_campaign_email
    ON marketing.email_clicks (campaign_id, email);

CREATE INDEX IF NOT EXISTS idx_email_clicks_email_time
    ON marketing.email_clicks (email, clicked_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_clicks_url
    ON marketing.email_clicks (url);

CREATE INDEX IF NOT EXISTS idx_email_clicks_recent
    ON marketing.email_clicks (clicked_at DESC);

COMMENT ON TABLE marketing.email_clicks IS
    'Append-only log of recipient link-click events. One row per redirect. '
    'Multiple clicks per recipient are normal and expected.';


INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:022',
    'click_tracking.schema_created',
    'marketing.email_clicks',
    jsonb_build_object(
        'note',
        'marketing.email_clicks created. Link-rewrite happens in '
        'tools/tracking.rewrite_links when MARKETING_TRACKING_BASE_URL is set. '
        'Without env-config, _send_paranoid keeps raw links (legacy path).'
    )
);

COMMIT;
