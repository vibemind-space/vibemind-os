-- ============================================================================
-- Marketing-Ops: investor_already_sent flag on marketing.emails
-- ============================================================================
-- A per-recipient one-shot lockout: once an investor / cold-outreach lead has
-- been contacted once, this flag prevents accidentally including them in
-- future campaigns. The flag stays sticky across audience-refresh cycles —
-- Audience-Builder filters MUST exclude `investor_already_sent = true`
-- unless explicitly overridden (which requires a separate UI confirmation).
--
-- Why a dedicated bool and not just count campaign_sends?
--   campaign_sends gets garbage-collected (we may purge old sends after a
--   retention window). This flag is the durable lockout that survives any
--   purge. It's also cheaper to filter on than a JOIN+COUNT.
--
-- Default: false (= safe to send). Set true on each successful first-time
-- delivery — handled by the send-worker via trigger or explicit UPDATE.
--
-- Apply:
--   docker cp 005_investor_sent_flag.sql vibemind_supabase-db.1.<id>:/tmp/
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -f /tmp/005_investor_sent_flag.sql

BEGIN;

ALTER TABLE marketing.emails
    ADD COLUMN IF NOT EXISTS investor_already_sent boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN marketing.emails.investor_already_sent IS
    'One-shot lockout flag. Once true, this email must NOT be included in '
    'any cold-outreach / investor campaign without explicit override. Set '
    'on first successful delivery. Sticky across audience refreshes.';

CREATE INDEX IF NOT EXISTS idx_emails_investor_sent
    ON marketing.emails(investor_already_sent)
    WHERE investor_already_sent = true;

-- Auto-flip the flag when a campaign_send transitions to "delivered" for the
-- first time per email. This is the canonical place to mark the lockout —
-- not in app code, where bugs could miss a flip.
CREATE OR REPLACE FUNCTION marketing.flip_investor_sent_on_delivery() RETURNS trigger AS $$
BEGIN
    -- Only flip on the transition NULL -> non-NULL delivered_at
    IF NEW.delivered_at IS NOT NULL AND (OLD.delivered_at IS NULL OR TG_OP = 'INSERT') THEN
        UPDATE marketing.emails
        SET investor_already_sent = true
        WHERE email = NEW.email
          AND investor_already_sent = false;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_flip_investor_sent ON marketing.campaign_sends;
CREATE TRIGGER trg_flip_investor_sent
    AFTER INSERT OR UPDATE OF delivered_at ON marketing.campaign_sends
    FOR EACH ROW
    EXECUTE FUNCTION marketing.flip_investor_sent_on_delivery();

-- Audit
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:005',
    'schema.add_column',
    'marketing.emails',
    jsonb_build_object(
        'column', 'investor_already_sent',
        'type', 'boolean NOT NULL DEFAULT false',
        'trigger', 'trg_flip_investor_sent on campaign_sends.delivered_at NULL->set',
        'index', 'idx_emails_investor_sent (partial WHERE true)',
        'purpose', 'one-shot lockout for cold-outreach recipients'
    )
);

COMMIT;

-- Verify:
--   \d marketing.emails  -- should show investor_already_sent boolean
--   SELECT COUNT(*) FROM marketing.emails WHERE investor_already_sent = false; -- = all imports
