-- ============================================================================
-- Marketing-Ops: UNIQUE (campaign_id, email) on campaign_sends
-- ============================================================================
-- Closes a Phase-2 send-worker safety gap: today campaign_sends has no
-- uniqueness constraint on (campaign_id, email), so a crashed send-worker
-- run that wrote sent_at for some rows and left campaign.status='queued'
-- would, on retry, re-INSERT new rows for the SAME recipients and re-send
-- to them.
--
-- With this constraint, the send-worker can claim recipients atomically:
--
--   INSERT INTO marketing.campaign_sends (campaign_id, email)
--   VALUES (...)
--   ON CONFLICT (campaign_id, email) DO NOTHING
--   RETURNING id
--
-- and SEND ONLY for the ids the INSERT actually returned. Retries become
-- safe: rows that already exist (because a prior partial run claimed them)
-- are silently skipped, never re-sent.
--
-- Apply order: AFTER 007 (which added campaign_sends.message_id) so the
-- existing partial unique idx_sends_msgid is preserved.
--
-- Safe on existing data: there are zero rows in campaign_sends today
-- (verified via SELECT COUNT(*)=0 in get_stats), but even if rows existed
-- the constraint can only fail if two rows already share (campaign_id,
-- email) -- the migration validates that pre-condition and aborts cleanly
-- if violated.
--
-- Apply:
--   docker cp 008_campaign_sends_unique.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/008_campaign_sends_unique.sql

BEGIN;

-- ─── 1. Pre-flight: confirm no existing duplicates would block the add ──
DO $$
DECLARE
    v_dupes int;
BEGIN
    SELECT COUNT(*) INTO v_dupes
    FROM (
        SELECT campaign_id, email, COUNT(*) AS n
        FROM marketing.campaign_sends
        GROUP BY campaign_id, email
        HAVING COUNT(*) > 1
    ) d;
    IF v_dupes > 0 THEN
        RAISE EXCEPTION
            '008 abort: % duplicate (campaign_id,email) pair(s) in campaign_sends. '
            'Resolve them before applying this constraint.', v_dupes;
    END IF;
END $$;

-- ─── 2. Add the UNIQUE constraint (idempotent) ──────────────────────────
-- Postgres rejects duplicate constraint names, so we guard via the
-- information_schema lookup.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_sends_campaign_email'
          AND conrelid = 'marketing.campaign_sends'::regclass
    ) THEN
        ALTER TABLE marketing.campaign_sends
            ADD CONSTRAINT uq_sends_campaign_email
            UNIQUE (campaign_id, email);
    END IF;
END $$;

COMMENT ON CONSTRAINT uq_sends_campaign_email ON marketing.campaign_sends IS
    'Atomic-claim guard for send-worker retries. Send-worker uses '
    'INSERT ... ON CONFLICT DO NOTHING RETURNING id and only sends to '
    'recipients whose rows it actually inserted. Prevents double-send '
    'after a crashed worker partial run.';

-- ─── 3. Audit ───────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:008',
    'schema.add_constraint',
    'marketing.campaign_sends',
    jsonb_build_object(
        'constraint_added', 'uq_sends_campaign_email UNIQUE(campaign_id, email)',
        'purpose',
            'send-worker atomic recipient claim; defeats double-send on crashed retry',
        'send_worker_contract',
            'INSERT ... ON CONFLICT (campaign_id,email) DO NOTHING RETURNING id; send only returned rows'
    )
);

COMMIT;
