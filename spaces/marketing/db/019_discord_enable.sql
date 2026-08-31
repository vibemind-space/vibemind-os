-- ============================================================================
-- Marketing-Ops: enable Discord as first OpenFang-mediated channel
-- ============================================================================
-- Schicht 4.5 — flip the migration-only hard gates that allow Discord
-- to actually receive marketing sends via OpenFang's `channel_send`
-- agent-tool.
--
-- PRE-REQUISITES (verified before this migration is applied):
--   - 018_openfang_adapter_mapping.sql applied (openfang_capable column exists)
--   - vibemind-os/openfang/agents/marketing-sender/agent.toml exists and the
--     agent registered in OpenFang with state=Running (HTTP probe ok)
--   - DISCORD_BOT_TOKEN already configured in OpenFang via
--     POST /api/channels/discord/configure (NOT in marketing's .env)
--   - At least one row in marketing.channel_recipient_allowlist for
--     (channel='discord', recipient_id=<discord channel id>) with a
--     valid hmac_sig (sign via tools/sign_recipient.py)
--   - MARKETING_PROPOSAL_API_KEY set in env for the send-worker
--
-- AFTER THIS MIGRATION:
--   - A marketing campaign with channel='discord' will route to
--     _send_openfang.py (legacy paths for email/telegram remain unchanged)
--   - DRY_RUN works without any other env (no MARKETING_SEND_ENABLED needed)
--   - LIVE requires MARKETING_SEND_ENABLED=true + confirm_token + freeze absent
--
-- This migration does NOT seed allowlist rows. The operator must run
-- tools/sign_recipient.py for each Discord channel_id that should
-- receive marketing-events. Example:
--   $env:MARKETING_PROPOSAL_API_KEY = "<32+ char secret>"
--   python -m spaces.marketing.tools.sign_recipient \
--     --channel discord \
--     --recipient-id <DISCORD_CH_DONE_ID> \
--     --approved-by felix \
--     --label "team-notify #done" \
--     --insert
--
-- Apply:
--   docker cp 019_discord_enable.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres \
--     -f /tmp/019_discord_enable.sql

BEGIN;

-- Flip the two migration-only gates for discord.
UPDATE marketing.channel_config
   SET openfang_capable = true,
       openfang_channel_name = COALESCE(openfang_channel_name, 'discord'),
       enabled = false           -- soft gate stays off; operator flips
 WHERE channel = 'discord';

-- Sanity assertion: the CHECK constraint from 018 requires
-- openfang_adapter IS NOT NULL when openfang_capable=true. discord's
-- openfang_adapter was set to 'discord.rs' in migration 015, so this is
-- a no-op assertion (just makes the contract visible in the migration).
DO $$
DECLARE
    v_adapter text;
BEGIN
    SELECT openfang_adapter INTO v_adapter
      FROM marketing.channel_config
     WHERE channel = 'discord';
    IF v_adapter IS NULL THEN
        RAISE EXCEPTION 'discord.openfang_adapter is NULL -- migration 015 missing';
    END IF;
END$$;

-- Audit row
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:019',
    'channel_config.discord_openfang_enabled',
    'marketing.channel_config',
    jsonb_build_object(
        'channel', 'discord',
        'openfang_capable', true,
        'enabled', false,
        'note',
        'Discord is now openfang_capable=true. Operator must set enabled=true '
        'on this row once tools/sign_recipient.py has populated '
        'channel_recipient_allowlist with the intended Discord channel IDs. '
        'A campaign with channel=''discord'' will dispatch via '
        '_send_openfang.py through the marketing-sender agent.'
    )
);

COMMIT;
