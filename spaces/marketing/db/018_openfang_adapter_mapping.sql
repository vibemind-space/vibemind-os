-- ============================================================================
-- Marketing-Ops: OpenFang channel-adapter bridge mapping
-- ============================================================================
-- Schicht 4 — multi-channel send via OpenFang
--
-- BEFORE this migration, every per-channel send required its own marketing-
-- side module with a full 12-gate stack (see _send_paranoid.py for email,
-- _send_telegram.py for telegram). Each new channel = full reimplementation
-- of bot-token-fetching, recipient-probing, rate-limiting, retry-logic.
--
-- AFTER this migration, marketing delegates the transport layer to OpenFang's
-- `channel_send` agent-tool, which already implements:
--   - credential storage (DPAPI-protected in ~/.openfang/config.toml)
--   - per-channel adapter logic (40+ adapters in openfang-channels crate)
--   - rate-limiting + retry + connection pooling
--   - file/image/thread-id support
--
-- Marketing-side STILL OWNS:
--   - kill-switch (gate 1, env)
--   - freeze-file (gate 1.5)
--   - allowlist (gate 6)
--   - confirm-token (gate 7)
--   - per-recipient probe is now OPTIONAL (OpenFang handles unreachable
--     recipients; we keep the probe-cache for known-good recipients only)
--   - atomic claim via campaign_sends UNIQUE constraint (gate 10)
--   - post-send audit (gate 12)
--
-- The OpenFang "marketing-sender" agent is the SINGLE entry-point into the
-- channel_send tool from marketing. Its system_prompt is instruct-only:
-- "Parse JSON input → exactly one channel_send call → return result.
-- Refuse anything else." So even if a marketing-side gate is bypassed,
-- the agent itself cannot be coerced into sending to non-listed channels.
--
-- THIS MIGRATION:
--   1. Adds `openfang_capable` column (mirror of send_implemented but for
--      the OpenFang transport path; both are migration-only).
--   2. Adds CHECK constraint: a channel can only be openfang_capable=true
--      if openfang_adapter IS NOT NULL.
--   3. Adds `openfang_channel_name` — the literal string passed as
--      channel_send's `channel` arg. Defaults to channel-column but can
--      override (e.g., 'gotify' vs 'gotify.rs').
--   4. NO channel is flipped to openfang_capable=true by this migration.
--      Each adapter-flip is a separate migration with its own review.
--
-- Apply:
--   docker cp 018_openfang_adapter_mapping.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres \
--     -f /tmp/018_openfang_adapter_mapping.sql

BEGIN;

-- ─── New columns ───────────────────────────────────────────────────────
ALTER TABLE marketing.channel_config
    ADD COLUMN IF NOT EXISTS openfang_capable      boolean      NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS openfang_channel_name text;

COMMENT ON COLUMN marketing.channel_config.openfang_capable IS
    'When true, this channel sends via OpenFang channel_send agent-tool '
    'instead of a marketing-side _send_<channel>.py module. Migration-only '
    '(never UPDATEd by application code). Implies openfang_adapter IS NOT NULL.';
COMMENT ON COLUMN marketing.channel_config.openfang_channel_name IS
    'Literal string passed as the channel_send tool''s `channel` arg. '
    'Falls back to the channel column when NULL.';

-- ─── Default openfang_channel_name from the channel column ────────────
-- For every existing row, default openfang_channel_name to the same
-- value as channel. Operator-overridable per row if a different name
-- is needed (e.g., 'mailcow' channel routed via OpenFang's 'email' adapter).
UPDATE marketing.channel_config
   SET openfang_channel_name = channel
 WHERE openfang_channel_name IS NULL;

-- ─── CHECK constraint: openfang_capable requires adapter ──────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'channel_config_openfang_capable_needs_adapter'
    ) THEN
        ALTER TABLE marketing.channel_config
            ADD CONSTRAINT channel_config_openfang_capable_needs_adapter
            CHECK (
                NOT openfang_capable
                OR (openfang_adapter IS NOT NULL
                    AND openfang_channel_name IS NOT NULL)
            );
    END IF;
END$$;

-- ─── send_implemented OR openfang_capable invariant ───────────────────
-- A channel must have ONE of the two transport paths to actually send.
-- Both can be true (legacy + new path coexist temporarily during migrations);
-- both can be false (channel listed but no implementation yet). The
-- send-worker dispatches on openfang_capable FIRST (preferred path),
-- falling back to legacy send_implemented modules.
COMMENT ON COLUMN marketing.channel_config.send_implemented IS
    'When true, a marketing-side tools/_send_<channel>.py module exists with '
    'its own 12-gate stack. Legacy path: email + telegram. Migration-only.';

-- ─── Index for dispatcher lookup ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_channel_config_openfang_capable
    ON marketing.channel_config (channel)
    WHERE openfang_capable = true;

-- ─── Signed recipient allowlist ───────────────────────────────────────
-- Equivalent to email's ALLOWED_DOMAINS / telegram's _ALLOWED_CHAT_IDS:
-- every (channel, recipient_id) pair that the OpenFang transport may
-- target. Each row carries an HMAC-SHA256 signature over a canonical
-- form, computed with MARKETING_PROPOSAL_API_KEY. The send-worker
-- verifies the signature on every snapshot; tampered rows are refused.
--
-- Why DB and not hardcoded:
--   - Discord channel IDs grow over time; recompile-per-recipient is friction.
--   - The signature blocks the SQL-side leak: an attacker who can UPDATE
--     channel_recipient_allowlist still cannot mint valid HMACs without
--     MARKETING_PROPOSAL_API_KEY.
--
-- Operator-side: see tools/sign_recipient.py (generates the hmac for a
-- canonical (channel, recipient_id, approved_by) tuple before INSERT).
CREATE TABLE IF NOT EXISTS marketing.channel_recipient_allowlist (
    channel       text        NOT NULL,
    recipient_id  text        NOT NULL,
    label         text,
    approved_by   text        NOT NULL,
    approved_at   timestamptz NOT NULL DEFAULT now(),
    hmac_sig      text        NOT NULL,
    revoked_at    timestamptz,
    notes         text,
    PRIMARY KEY (channel, recipient_id),
    -- channel must be a registered marketing channel
    FOREIGN KEY (channel) REFERENCES marketing.channel_config(channel)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

COMMENT ON TABLE marketing.channel_recipient_allowlist IS
    'Signed allowlist of (channel, recipient_id) pairs the OpenFang send-worker '
    'may target. hmac_sig is HMAC-SHA256 with MARKETING_PROPOSAL_API_KEY over '
    '"allowlist-v1\n{channel}\n{recipient_id}\n{approved_by}". Verified on every '
    'snapshot. Rows without revoked_at AND with valid sig are eligible.';

COMMENT ON COLUMN marketing.channel_recipient_allowlist.hmac_sig IS
    'Hex sha256 HMAC over canonical form: '
    '"allowlist-v1\\n<channel>\\n<recipient_id>\\n<approved_by>". '
    'Computed with MARKETING_PROPOSAL_API_KEY. send-worker REFUSES sends '
    'to recipients whose sig does not verify (incl. tampering, key rotation).';

CREATE INDEX IF NOT EXISTS idx_channel_recipient_allowlist_active
    ON marketing.channel_recipient_allowlist (channel)
    WHERE revoked_at IS NULL;

-- ─── campaign_sends_openfang (one row per (campaign, channel, recipient)) ──
-- Generic counterpart to marketing.campaign_sends (email) and
-- marketing.campaign_sends_telegram. Atomic claim happens via the
-- composite PRIMARY KEY: ON CONFLICT DO NOTHING means a parallel
-- worker cannot double-send to the same recipient even if two send
-- runs interleave.
CREATE TABLE IF NOT EXISTS marketing.campaign_sends_openfang (
    campaign_id           uuid        NOT NULL REFERENCES marketing.campaigns(id) ON DELETE CASCADE,
    channel               text        NOT NULL REFERENCES marketing.channel_config(channel) ON UPDATE CASCADE,
    recipient_id          text        NOT NULL,
    claimed_at            timestamptz NOT NULL DEFAULT now(),
    sent_at               timestamptz,
    bounced_at            timestamptz,
    bounce_reason         text,
    openfang_message_ref  text,
    PRIMARY KEY (campaign_id, channel, recipient_id)
);

COMMENT ON TABLE marketing.campaign_sends_openfang IS
    'One row per (campaign, channel, recipient) successfully claimed by the '
    'OpenFang send-worker. PK is the atomic claim primitive: ON CONFLICT DO '
    'NOTHING blocks double-sends. sent_at / bounced_at are mutually exclusive '
    'final states.';

CREATE INDEX IF NOT EXISTS idx_campaign_sends_openfang_campaign
    ON marketing.campaign_sends_openfang (campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_sends_openfang_channel
    ON marketing.campaign_sends_openfang (channel)
    WHERE sent_at IS NOT NULL;

-- ─── v_campaign_metrics extension SKIPPED ─────────────────────────────
-- The existing v_campaign_metrics view (created by an earlier migration
-- in this branch) has a richer schema than this migration tried to
-- replace. CREATE OR REPLACE VIEW with a column-count change errors out,
-- and even if it succeeded the dropped columns would break other queries.
-- We rely on v_campaign_performance (migration 023) for openfang-channel
-- metrics instead.

-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:018',
    'channel_config.openfang_bridge_columns_added',
    'marketing.channel_config',
    jsonb_build_object(
        'note',
        'openfang_capable + openfang_channel_name columns added. '
        'No channel flipped to openfang_capable=true by this migration. '
        'Each per-channel flip is a separate migration (e.g., 019_discord_enable.sql).'
    )
);

COMMIT;
