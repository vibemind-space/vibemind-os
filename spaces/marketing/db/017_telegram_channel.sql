-- ============================================================================
-- Marketing-Ops: Telegram channel readiness (second real send-channel)
-- ============================================================================
-- This is a HIGH-RISK migration. It adds the SECOND code path that can
-- actually send a message to a real recipient. Read the safeguards
-- carefully before approving any change to this file.
--
-- Design decisions:
--
--   - Telegram recipients are chat_ids (int64), NOT email addresses.
--     Two separate tables (telegram_recipients, campaign_sends_telegram)
--     parallel to (emails, campaign_sends) keep the schemas clean.
--     Existing email send-path is UNAFFECTED.
--
--   - The hard send-eligibility gate stays on marketing.channel_config:
--     send_implemented=true for telegram ONLY after the per-channel
--     send module (tools/_send_telegram.py) exists AND passes review.
--     This migration flips that flag. The flip is reviewable in git.
--
--   - chat_id allowlist is HARDCODED IN PYTHON CODE
--     (spaces/marketing/tools/_send_telegram.py:_ALLOWED_CHAT_IDS), not
--     in the DB. Same model as ALLOWED_DOMAINS for email. Operator
--     cannot widen it via SQL.
--
--   - investor_already_sent equivalent is NOT replicated for Telegram.
--     The whole purpose of investor-lockout was to prevent the same
--     person being mailed twice with cold-outreach; Telegram messages
--     are an opt-in channel by construction (you have to start a chat
--     with the bot first), so the lockout concept doesn't carry over.
--     The bot can ONLY send to chat_ids that have messaged it first;
--     this is a Telegram API guarantee, not just policy.
--
--   - DKIM/SPF/DMARC don't apply. Replaced by Bot Token + chat_id
--     allowlist at gate level.
--
-- Apply:
--   docker cp 017_telegram_channel.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/017_telegram_channel.sql

BEGIN;

-- ─── 1. Telegram recipients table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.telegram_recipients (
    chat_id            bigint PRIMARY KEY,                   -- Telegram chat_id (int64)
    handle             text REFERENCES marketing.accounts(handle) ON DELETE CASCADE,
    username           text,                                 -- Telegram @handle (optional)
    first_name         text DEFAULT '',
    last_name          text DEFAULT '',
    language_code      text,                                 -- e.g. 'de', 'en'
    is_bot             boolean DEFAULT false,
    -- Whether the recipient has messaged the bot first. Telegram
    -- bot-API requires this; we cache the answer here.
    opt_in_at          timestamptz NOT NULL DEFAULT now(),
    -- Mirrors emails.unsubscribed_at -- explicit opt-out beyond the
    -- Telegram-API-level opt-in guarantee.
    blocked_at         timestamptz,
    last_engagement_at timestamptz,
    created_at         timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telegram_handle
    ON marketing.telegram_recipients(handle);
CREATE INDEX IF NOT EXISTS idx_telegram_active
    ON marketing.telegram_recipients(chat_id)
    WHERE blocked_at IS NULL;

COMMENT ON TABLE marketing.telegram_recipients IS
    'Telegram chat_id mapping. opt_in_at is the moment the recipient '
    'first messaged the bot (Telegram API prerequisite). blocked_at '
    'is application-side opt-out.';

GRANT ALL ON marketing.telegram_recipients TO service_role;


-- ─── 2. Telegram send-tracking table ───────────────────────────────────
-- Parallel to marketing.campaign_sends but keyed on chat_id.
CREATE TABLE IF NOT EXISTS marketing.campaign_sends_telegram (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     uuid NOT NULL REFERENCES marketing.campaigns(id) ON DELETE CASCADE,
    chat_id         bigint NOT NULL REFERENCES marketing.telegram_recipients(chat_id) ON DELETE CASCADE,
    queued_at       timestamptz DEFAULT now(),
    sent_at         timestamptz,
    -- Telegram's API returns a message_id on success; we store it for
    -- future reply-linkage / edit / delete operations.
    telegram_message_id bigint,
    bounced_at      timestamptz,        -- bot-API error response
    bounce_reason   text,
    replied_at      timestamptz,        -- when recipient replied to bot
    blocked_at      timestamptz,        -- recipient blocked the bot
    open_count      integer DEFAULT 0,
    click_count     integer DEFAULT 0,
    CONSTRAINT uq_telegram_sends UNIQUE (campaign_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_telegram_sends_campaign
    ON marketing.campaign_sends_telegram(campaign_id);
CREATE INDEX IF NOT EXISTS idx_telegram_sends_chat
    ON marketing.campaign_sends_telegram(chat_id);
CREATE INDEX IF NOT EXISTS idx_telegram_sends_sent
    ON marketing.campaign_sends_telegram(sent_at);

COMMENT ON TABLE marketing.campaign_sends_telegram IS
    'Telegram-channel send-tracking. Parallel to campaign_sends but '
    'chat_id-keyed. Same atomic-claim pattern via UNIQUE(campaign_id, chat_id).';

GRANT ALL ON marketing.campaign_sends_telegram TO service_role;


-- ─── 3. Helper view: campaign metrics across BOTH channels ─────────────
-- Updates v_campaign_metrics to include telegram. Drop-and-recreate
-- because the column list changes.
DROP VIEW IF EXISTS marketing.v_campaign_metrics;
CREATE VIEW marketing.v_campaign_metrics AS
SELECT
    c.id                                                 AS campaign_id,
    c.name                                               AS campaign_name,
    c.status                                             AS campaign_status,
    c.channel                                            AS campaign_channel,
    c.audience_id,
    -- Email-channel counts
    COUNT(cs.id) FILTER (WHERE cs.id IS NOT NULL)                          AS email_sends_total,
    COUNT(cs.id) FILTER (WHERE cs.sent_at IS NOT NULL)                     AS email_sends_sent,
    COUNT(cs.id) FILTER (WHERE cs.delivered_at IS NOT NULL)                AS email_sends_delivered,
    COUNT(cs.id) FILTER (WHERE cs.bounced_at IS NOT NULL)                  AS email_sends_bounced,
    COUNT(cs.id) FILTER (WHERE cs.replied_at IS NOT NULL)                  AS email_sends_replied,
    -- Telegram-channel counts
    COUNT(tg.id) FILTER (WHERE tg.id IS NOT NULL)                          AS telegram_sends_total,
    COUNT(tg.id) FILTER (WHERE tg.sent_at IS NOT NULL)                     AS telegram_sends_sent,
    COUNT(tg.id) FILTER (WHERE tg.bounced_at IS NOT NULL)                  AS telegram_sends_bounced,
    COUNT(tg.id) FILTER (WHERE tg.replied_at IS NOT NULL)                  AS telegram_sends_replied,
    GREATEST(MAX(cs.sent_at), MAX(tg.sent_at))                             AS last_send_at
FROM marketing.campaigns c
LEFT JOIN marketing.campaign_sends cs          ON cs.campaign_id = c.id
LEFT JOIN marketing.campaign_sends_telegram tg ON tg.campaign_id = c.id
GROUP BY c.id, c.name, c.status, c.channel, c.audience_id;

GRANT SELECT ON marketing.v_campaign_metrics TO service_role;


-- ─── 4. Flip telegram to send_implemented=true ────────────────────────
-- This is the hard gate. After this UPDATE, send-worker accepts
-- campaigns with channel='telegram'. The soft gate (enabled=true)
-- is still operator-controlled. Updated_at fires via trg_channel_
-- config_updated_at (migration 015).
UPDATE marketing.channel_config
SET send_implemented = true,
    notes = 'Per-channel send module: spaces/marketing/tools/_send_telegram.py. '
            'Allowlist hardcoded (chat_ids). Bot Token in TELEGRAM_BOT_TOKEN env.'
WHERE channel = 'telegram';


-- ─── 5. Audit ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:017',
    'schema.add_telegram_channel',
    'marketing',
    jsonb_build_object(
        'tables_added', jsonb_build_array(
            'marketing.telegram_recipients',
            'marketing.campaign_sends_telegram'
        ),
        'views_updated', jsonb_build_array(
            'marketing.v_campaign_metrics (now spans email + telegram)'
        ),
        'channels_send_implemented_flipped',
            jsonb_build_array('telegram'),
        'safeguards', jsonb_build_array(
            'chat_id allowlist hardcoded in _send_telegram.py',
            'Bot Token in TELEGRAM_BOT_TOKEN env (not in DB)',
            'Telegram API itself requires opt-in (recipient must message bot first)',
            'enabled=false by default; operator must flip to send live',
            '12-gate stack adapted: kill-switch + FREEZE + token + per-chat probe + post-send audit',
            'Email path UNCHANGED; new tables are isolated'
        ),
        'phase_1_contract',
            'Email no-mail-out invariant remains; Telegram is a NEW path '
            'with its own no-message-out invariant via the hardcoded allowlist'
    )
);

COMMIT;
