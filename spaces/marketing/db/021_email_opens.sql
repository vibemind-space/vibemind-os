-- ============================================================================
-- Marketing-Ops: open-tracking (Schicht 5.1)
-- ============================================================================
-- Brevo-equivalent recipient open-tracking via 1x1 GIF pixel.
--
-- Flow:
--   1. _send_paranoid renders template; if tracking_enabled on the template,
--      it injects an <img src="{MARKETING_TRACKING_BASE_URL}/t/o/{token}" />
--      at the END of the HTML body (text/plain bodies don't carry images).
--   2. Recipient's mail client fetches the pixel.
--   3. /t/o/{token} endpoint:
--        - HMAC-verifies token (MARKETING_TRACKING_SECRET)
--        - INSERTs row in marketing.email_opens
--        - Returns 1x1 transparent GIF (43 bytes)
--        - emits webhook event 'open'
--   4. webhook_delivery worker fans 'open' events to subscriptions.
--
-- Multiple opens by the same recipient = multiple rows (we WANT the timeline).
-- Dedup happens at the view layer (v_recipient_engagement uses COUNT DISTINCT).
--
-- DSGVO note:
--   Tracking pixels in DE are cookie/Telemedien-rechtlich grau. Mitigation:
--   the template-render only injects the pixel when
--   marketing.templates.tracking_enabled = true. Transactional templates
--   (opt-in confirm, password-reset) can run with tracking_enabled = false.
--   Future migration: per-recipient tracking_consent_given_at on
--   marketing.emails, gate pixel injection on it too.
--
-- Apply:
--   docker cp 021_email_opens.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/021_email_opens.sql

BEGIN;

-- ─── opens table ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.email_opens (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     uuid        NOT NULL REFERENCES marketing.campaigns(id) ON DELETE CASCADE,
    email           citext      NOT NULL,
    opened_at       timestamptz NOT NULL DEFAULT now(),
    user_agent      text,
    ip              inet,
    msgid_core      text                              -- correlation key (the prefix in <msgid_core@vibemind.space>)
);

CREATE INDEX IF NOT EXISTS idx_email_opens_campaign_email
    ON marketing.email_opens (campaign_id, email);

CREATE INDEX IF NOT EXISTS idx_email_opens_email_time
    ON marketing.email_opens (email, opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_opens_recent
    ON marketing.email_opens (opened_at DESC);

COMMENT ON TABLE marketing.email_opens IS
    'Append-only log of recipient email-open events. One row per pixel-fetch. '
    'Multi-fetch is normal (re-opening the email in different clients counts '
    'multiple times). Dedup at the view layer.';

COMMENT ON COLUMN marketing.email_opens.msgid_core IS
    'The local-part of the RFC 5322 Message-ID our send-worker stamped onto '
    'the outgoing mail (e.g. "abc12345-deadbeef" in <abc12345-deadbeef@vibemind.space>). '
    'Lets us correlate opens back to specific send attempts even when a recipient '
    'received multiple campaigns.';


-- ─── tracking_enabled column on templates ────────────────────────────
ALTER TABLE marketing.templates
    ADD COLUMN IF NOT EXISTS tracking_enabled boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN marketing.templates.tracking_enabled IS
    'When true, _send_paranoid injects an <img> open-pixel + rewrites <a href> '
    'links via the click-tracker (Schicht 5.2). Defaults to FALSE -- operator '
    'must opt-in per template. Transactional templates (opt-in, reset, receipts) '
    'stay tracking-free.';


-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:021',
    'open_tracking.schema_created',
    'marketing.email_opens',
    jsonb_build_object(
        'note',
        'marketing.email_opens created. templates.tracking_enabled column added '
        '(DEFAULT false -- migration is safe, no existing template starts tracking). '
        'Pixel injection wires up in _send_paranoid.py when MARKETING_TRACKING_BASE_URL '
        'env is set.'
    )
);

COMMIT;
