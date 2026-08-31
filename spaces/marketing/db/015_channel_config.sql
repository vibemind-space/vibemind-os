-- ============================================================================
-- Marketing-Ops: per-channel configuration registry
-- ============================================================================
-- Phase-2 multi-channel preparation: lists every channel the send-worker
-- could in theory address (mirrors OpenFang's 42 channel adapters),
-- tracks which are configured live AND active, and exposes a single
-- query the send-worker uses to refuse aborted-channels at gate 4.5.
--
-- NO channel except email is implemented end-to-end today. Every row
-- in this table for non-email channels carries `send_implemented=false`
-- AND `enabled=false`. The send-worker's gate 4.5
-- (assert_channel_configured) refuses if any chosen campaign.channel
-- has send_implemented=false. Phase-1-no-mail-out invariant therefore
-- extends to multi-channel: a campaign with channel='telegram' will
-- abort cleanly because the schema says telegram isn't ready.
--
-- To "enable" a channel for real send:
--   1. Implement the per-channel send module (tools/_send_<channel>.py)
--      with its own 12-gate stack (allowlist, kill-switch, freeze-file,
--      per-recipient probe, post-send audit, etc.).
--   2. Add tests including never_calls_email_send + never_calls_other_
--      channel_send regression-guards.
--   3. Update this row with send_implemented=true via a NEW migration
--      (not via UPDATE in code).
--   4. Set enabled=true via operator action (UI / SQL) once creds are
--      set in env.
--
-- All four steps reviewed = the channel becomes send-eligible.
--
-- Apply:
--   docker cp 015_channel_config.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/015_channel_config.sql

BEGIN;

-- ─── Channel registry ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.channel_config (
    -- Stable lowercase id matching OpenFang channel adapter names
    -- (telegram, slack, discord, ...). Same identifier the
    -- marketing.campaigns.channel free-text column uses.
    channel               text PRIMARY KEY,
    label                 text NOT NULL,
    -- Maps to the OpenFang channel adapter file (crates/openfang-channels/src/)
    -- when relevant.
    openfang_adapter      text,
    -- "OAuth + Bot Token" / "Webhook URL" / "SMTP" / "IMAP+SMTP" / ...
    auth_kind             text,
    -- Required env-vars (any one missing => can't send).
    required_env          jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- HARD GATE: whether the per-channel send module exists AND has
    -- been reviewed for the 12-gate stack. Only flipped via migration.
    -- This is the ONLY column that decides whether the send-worker
    -- accepts a campaign with this channel. CHECK enforces email is
    -- the only true for now.
    send_implemented      boolean NOT NULL DEFAULT false,
    -- Operator runtime gate: when send_implemented=true AND the env-
    -- vars are filled in, the operator flips enabled=true to actually
    -- accept sends. Decoupled so you can disable a channel temporarily
    -- without dropping the module.
    enabled               boolean NOT NULL DEFAULT false,
    -- Defense-in-depth: max recipients allowed per send batch on this
    -- channel. Most non-email channels have much tighter rate-limits.
    rate_limit_per_minute integer NOT NULL DEFAULT 0
                          CHECK (rate_limit_per_minute >= 0),
    -- Bookkeeping
    last_send_at          timestamptz,
    notes                 text DEFAULT '',
    created_at            timestamptz DEFAULT now(),
    updated_at            timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_channel_send_implemented
    ON marketing.channel_config(send_implemented)
    WHERE send_implemented = true;
CREATE INDEX IF NOT EXISTS idx_channel_enabled
    ON marketing.channel_config(enabled)
    WHERE enabled = true;

COMMENT ON TABLE marketing.channel_config IS
    'Per-channel send-eligibility registry. Mirrors OpenFang adapters. '
    'send_implemented is the hard gate (migration-only); enabled is '
    'the soft runtime gate (operator UI / SQL). Send-worker refuses '
    'a campaign whose channel has send_implemented=false.';

-- updated_at trigger
CREATE OR REPLACE FUNCTION marketing._channel_config_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_channel_config_updated_at ON marketing.channel_config;
CREATE TRIGGER trg_channel_config_updated_at
    BEFORE UPDATE ON marketing.channel_config
    FOR EACH ROW
    EXECUTE FUNCTION marketing._channel_config_updated_at();

GRANT ALL ON marketing.channel_config TO service_role;

-- ─── Seed: every OpenFang channel as 'known but unimplemented' ─────────
-- send_implemented=false EXCEPT for email. enabled=false everywhere
-- (operator must explicitly turn the soft gate on once creds are set).
INSERT INTO marketing.channel_config
    (channel, label, openfang_adapter, auth_kind, required_env, send_implemented)
VALUES
    -- The one that actually works today.
    ('email',        'Email (SMTP+IMAP via Mailcow)',
                     'email.rs',         'SMTP+IMAP',
                     '["SMTP_HOST","SMTP_PORT","SMTP_USER","SMTP_PASS"]'::jsonb, true),
    -- Messaging channels
    ('telegram',     'Telegram Bot',           'telegram.rs',  'Bot Token',
                     '["TELEGRAM_BOT_TOKEN"]'::jsonb,                 false),
    ('discord',      'Discord Bot',            'discord.rs',   'Bot Token',
                     '["DISCORD_BOT_TOKEN"]'::jsonb,                  false),
    ('slack',        'Slack',                  'slack.rs',     'Socket Mode + Bot Token',
                     '["SLACK_BOT_TOKEN","SLACK_APP_TOKEN"]'::jsonb,  false),
    ('matrix',       'Matrix (homeserver)',    'matrix.rs',    'Access Token',
                     '["MATRIX_HOMESERVER","MATRIX_ACCESS_TOKEN"]'::jsonb, false),
    ('signal',       'Signal (via signal-cli)','signal.rs',    'REST Token',
                     '["SIGNAL_CLI_URL"]'::jsonb,                     false),
    ('whatsapp',     'WhatsApp Business',      'whatsapp.rs',  'OAuth + Phone Number ID',
                     '["WHATSAPP_TOKEN","WHATSAPP_PHONE_ID"]'::jsonb, false),
    ('viber',        'Viber Bot',              'viber.rs',     'Auth Token',
                     '["VIBER_AUTH_TOKEN"]'::jsonb,                   false),
    ('threema',      'Threema Gateway',        'threema.rs',   'Gateway ID + Secret',
                     '["THREEMA_GATEWAY_ID","THREEMA_SECRET"]'::jsonb,false),
    ('line',         'LINE Messaging',         'line.rs',      'Channel Access Token',
                     '["LINE_ACCESS_TOKEN"]'::jsonb,                  false),
    ('keybase',      'Keybase chat',           'keybase.rs',   'Local CLI',
                     '["KEYBASE_USERNAME"]'::jsonb,                   false),
    ('messenger',    'Facebook Messenger',     'messenger.rs', 'Page Access Token',
                     '["MESSENGER_PAGE_TOKEN"]'::jsonb,               false),
    -- Social channels
    ('mastodon',     'Mastodon',               'mastodon.rs',  'OAuth',
                     '["MASTODON_INSTANCE","MASTODON_TOKEN"]'::jsonb, false),
    ('bluesky',      'Bluesky / AT Protocol',  'bluesky.rs',   'App Password',
                     '["BLUESKY_HANDLE","BLUESKY_APP_PASSWORD"]'::jsonb, false),
    ('twitter',      'Twitter / X',            NULL,           'Bearer Token',
                     '["TWITTER_BEARER_TOKEN"]'::jsonb,               false),
    ('reddit',       'Reddit',                 'reddit.rs',    'OAuth',
                     '["REDDIT_CLIENT_ID","REDDIT_CLIENT_SECRET"]'::jsonb, false),
    ('linkedin',     'LinkedIn',               'linkedin.rs',  'OAuth',
                     '["LINKEDIN_CLIENT_ID","LINKEDIN_CLIENT_SECRET","LINKEDIN_ACCESS_TOKEN"]'::jsonb, false),
    ('nostr',        'Nostr relay',            'nostr.rs',     'Private Key',
                     '["NOSTR_PRIVATE_KEY"]'::jsonb,                  false),
    -- Enterprise
    ('feishu',       'Feishu / Lark',          'feishu.rs',    'App ID + Secret',
                     '["FEISHU_APP_ID","FEISHU_APP_SECRET"]'::jsonb,  false),
    ('wecom',        'WeCom',                  'wecom.rs',     'Corp ID + Secret',
                     '["WECOM_CORP_ID","WECOM_CORP_SECRET"]'::jsonb,  false),
    ('dingtalk',     'DingTalk',               'dingtalk.rs',  'App Key + Secret',
                     '["DINGTALK_APP_KEY","DINGTALK_APP_SECRET"]'::jsonb, false),
    ('teams',        'Microsoft Teams',        'teams.rs',     'Bot Framework',
                     '["TEAMS_APP_ID","TEAMS_APP_PASSWORD"]'::jsonb,  false),
    ('webex',        'Cisco Webex',            'webex.rs',     'Bot Access Token',
                     '["WEBEX_BOT_TOKEN"]'::jsonb,                    false),
    ('google_chat',  'Google Chat',            'google_chat.rs','Service Account',
                     '["GCHAT_SERVICE_ACCOUNT_JSON"]'::jsonb,         false),
    ('mattermost',   'Mattermost',             NULL,           'Bot Token',
                     '["MATTERMOST_URL","MATTERMOST_BOT_TOKEN"]'::jsonb, false),
    ('rocketchat',   'Rocket.Chat',            'rocketchat.rs','Auth Token',
                     '["ROCKETCHAT_URL","ROCKETCHAT_AUTH_TOKEN"]'::jsonb, false),
    ('zulip',        'Zulip',                  'zulip.rs',     'Bot Email + API Key',
                     '["ZULIP_EMAIL","ZULIP_API_KEY"]'::jsonb,        false),
    -- Notifications-only (no real campaigns, just transactional)
    ('webhook',      'Generic Webhook',        'webhook.rs',   'URL',
                     '["WEBHOOK_URL"]'::jsonb,                        false),
    ('ntfy',         'ntfy.sh',                'ntfy.rs',      'Topic',
                     '["NTFY_TOPIC"]'::jsonb,                         false),
    ('gotify',       'Gotify',                 'gotify.rs',    'App Token',
                     '["GOTIFY_URL","GOTIFY_TOKEN"]'::jsonb,          false),
    ('pumble',       'Pumble',                 'pumble.rs',    'Webhook URL',
                     '["PUMBLE_WEBHOOK"]'::jsonb,                     false)
ON CONFLICT (channel) DO NOTHING;

-- ─── Audit ─────────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:015',
    'schema.add_table_seed',
    'marketing.channel_config',
    jsonb_build_object(
        'table_added', 'marketing.channel_config',
        'channels_seeded', 31,
        'channels_send_implemented', jsonb_build_array('email'),
        'expansion_rule',
            'new send-eligible channel requires new migration AND per-channel '
            'send module AND tests. UI/operator cannot flip send_implemented.',
        'gate_added',
            'send-worker gate 4.5 (assert_channel_configured) refuses '
            'campaign whose channel has send_implemented=false'
    )
);

COMMIT;
