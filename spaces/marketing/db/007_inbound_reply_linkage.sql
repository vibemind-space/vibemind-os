-- ============================================================================
-- Marketing-Ops: outbound Message-ID storage + automatic reply-linkage
-- ============================================================================
-- Closes the inbound -> outbound loop introduced by Worker C (IMAP sync).
--
-- Adds:
--   1. marketing.campaign_sends.message_id (text, NULLABLE) — the RFC 5322
--      Message-ID of the outbound mail, stored WITHOUT angle brackets to
--      match Worker C's normalization (worker_imap_sync.py:344-345 strips
--      "<>" from both Message-ID and In-Reply-To). The send-worker MUST
--      strip "<>" before writing this column.
--
--   2. Partial unique index idx_sends_msgid — supports O(log n) lookup from
--      inbound_messages.in_reply_to, enforces one outbound Message-ID per
--      send-row, ignores NULL (queued-but-not-yet-sent rows).
--
--   3. AFTER INSERT trigger trg_link_inbound_to_send on inbound_messages
--      that auto-populates inbound_messages.linked_send_id (and the matching
--      campaign_sends.replied_at) whenever the inbound has an in_reply_to
--      pointing at a known outbound Message-ID.
--
-- Loop prevention (split-GUC pattern):
--   The trigger function does TWO writes (UPDATE inbound_messages,
--   UPDATE campaign_sends). It MUST NOT suppress BOTH emits — the
--   campaign_sends.replied_at change is a real business-state transition
--   ("a send got a reply") and is THE point of this migration: Worker A
--   should propagate it to the markdown vault so the reply-rate metric
--   reaches the file layer.
--
--   Therefore: the GUC suppression is wrapped ONLY around the inbound
--   UPDATE (which would otherwise double-emit the same inbound row that
--   the original INSERT already emitted). The campaign_sends UPDATE runs
--   with the prior GUC value restored, so it emits ONE outbox row as
--   intended.
--
--   The function saves and restores any caller-set sync_origin so a future
--   Worker-B path that sets sync_origin='fs' around the inbound INSERT
--   isn't clobbered.
--
-- Trigger fire order (alphabetical):
--   trg_emit_sync_inbound_messages fires FIRST (e < l) — produces one
--   outbox row with payload.linked_send_id=NULL (a stale snapshot).
--   trg_link_inbound_to_send fires SECOND — populates linked_send_id +
--   campaign_sends.replied_at, suppresses the inbound double-emit, lets
--   the campaign_sends emit through.
--
--   Consumers (Worker A) MUST re-query live state by row_key rather than
--   trusting payload.linked_send_id. If Worker A trusts the payload, file
--   a follow-up to fix Worker A — do NOT attempt to fix it by reordering
--   or coalescing emits here.
--
-- Send-worker contract (for the future send_campaign implementation):
--   (a) Write sent_at + message_id in the SAME UPDATE (one outbox row).
--   (b) Strip leading '<' and trailing '>' before INSERT.
--   (c) Generate a fresh Message-ID on retries — the partial unique
--       idx_sends_msgid will reject reuse.
--
-- Idempotent backfill:
--   The migration runs a one-shot UPDATE that links any pre-existing
--   inbound_messages rows whose in_reply_to matches a campaign_sends row
--   that already has message_id set. Safe to re-run — only NULLs are
--   touched. (At first apply this finds 0 rows because no send-row has
--   message_id yet; the send-worker populates that going forward.)
--
-- Apply:
--   docker cp 007_inbound_reply_linkage.sql vibemind_supabase-db.1.<id>:/tmp/
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -f /tmp/007_inbound_reply_linkage.sql

BEGIN;

-- ─── 1. New column on campaign_sends ─────────────────────────────────────
ALTER TABLE marketing.campaign_sends
    ADD COLUMN IF NOT EXISTS message_id text;

COMMENT ON COLUMN marketing.campaign_sends.message_id IS
    'RFC 5322 Message-ID of the outbound mail, stored WITHOUT angle brackets '
    '(e.g. "abc123@vibemind.space", NOT "<abc123@vibemind.space>"). The '
    'send-worker MUST strip "<>" before writing -- matches Worker C''s '
    'normalization (worker_imap_sync.py:344-345). Used to join '
    'inbound_messages.in_reply_to -> campaign_sends.id for reply tracking.';

-- ─── 2. Partial unique index for fast in_reply_to lookups ────────────────
CREATE UNIQUE INDEX IF NOT EXISTS idx_sends_msgid
    ON marketing.campaign_sends(message_id)
    WHERE message_id IS NOT NULL;

-- Optional reporting index for "campaigns by reply-rate" queries.
CREATE INDEX IF NOT EXISTS idx_sends_replied
    ON marketing.campaign_sends(replied_at)
    WHERE replied_at IS NOT NULL;

-- ─── 3. Reply-linkage trigger function (split-GUC) ───────────────────────
CREATE OR REPLACE FUNCTION marketing.link_inbound_to_send() RETURNS trigger AS $$
DECLARE
    matched_send_id uuid;
    prior_origin    text;
BEGIN
    -- Defensive guards: empty/null in_reply_to or already linked -> no-op.
    IF NEW.in_reply_to IS NULL OR NEW.in_reply_to = '' THEN
        RETURN NEW;
    END IF;
    IF NEW.linked_send_id IS NOT NULL THEN
        RETURN NEW;
    END IF;

    -- Look up the originating send. Uses partial unique idx_sends_msgid.
    -- Defensive: also exclude '' just in case a buggy writer ever lands
    -- (the partial unique index protects against NULL but not '').
    SELECT id INTO matched_send_id
      FROM marketing.campaign_sends
     WHERE message_id = NEW.in_reply_to
       AND message_id IS NOT NULL
       AND message_id <> ''
     LIMIT 1;

    IF matched_send_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Save the caller's sync_origin so we can restore it (don't clobber
    -- a Worker-B path that's already in an 'fs'-origin transaction).
    BEGIN
        prior_origin := current_setting('marketing.sync_origin', true);
    EXCEPTION WHEN OTHERS THEN
        prior_origin := '';
    END;

    -- Suppress emit ONLY for the inbound-row UPDATE: that would otherwise
    -- be a spurious second outbox row for the SAME inbound (the INSERT's
    -- own emit-trigger already produced one).
    PERFORM set_config('marketing.sync_origin', 'fs', true);
    UPDATE marketing.inbound_messages
       SET linked_send_id = matched_send_id
     WHERE id = NEW.id
       AND linked_send_id IS NULL;

    -- Restore prior origin BEFORE updating campaign_sends so that change
    -- DOES emit one outbox row -- that's the inbound->outbound reply-rate
    -- signal Worker A needs to surface in the markdown vault.
    PERFORM set_config('marketing.sync_origin', COALESCE(prior_origin, ''), true);

    -- Close the inbound -> outbound metric loop: stamp replied_at on the
    -- send-row (first reply wins via COALESCE). trg_flip_investor_sent
    -- watches delivered_at only (005:53-56 -- the OF clause restricts to
    -- delivered_at), so this UPDATE does NOT touch the sticky lockout.
    UPDATE marketing.campaign_sends
       SET replied_at = COALESCE(replied_at, NEW.received_at, now())
     WHERE id = matched_send_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_link_inbound_to_send ON marketing.inbound_messages;
CREATE TRIGGER trg_link_inbound_to_send
    AFTER INSERT ON marketing.inbound_messages
    FOR EACH ROW
    EXECUTE FUNCTION marketing.link_inbound_to_send();

-- ─── 4. Idempotent backfill for pre-existing rows ────────────────────────
-- Bypass emit for the backfill UPDATEs -- backfill is "internal", not a
-- real DB-origin change to propagate. We don't need split-GUC here
-- because backfill never touches new rows that downstream consumers
-- haven't already seen.
SELECT set_config('marketing.sync_origin', 'fs', true);

WITH linked AS (
    UPDATE marketing.inbound_messages im
       SET linked_send_id = cs.id
      FROM marketing.campaign_sends cs
     WHERE im.linked_send_id IS NULL
       AND im.in_reply_to IS NOT NULL
       AND im.in_reply_to <> ''
       AND im.in_reply_to = cs.message_id
       AND cs.message_id IS NOT NULL
     RETURNING im.id, cs.id AS send_id, im.received_at
)
UPDATE marketing.campaign_sends cs
   SET replied_at = COALESCE(cs.replied_at, l.received_at)
  FROM linked l
 WHERE cs.id = l.send_id;

SELECT set_config('marketing.sync_origin', '', true);

-- ─── 5. Audit ────────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:007',
    'schema.add_column+trigger',
    'marketing.campaign_sends,marketing.inbound_messages',
    jsonb_build_object(
        'column_added', jsonb_build_object(
            'marketing.campaign_sends.message_id', 'text NULL (no angle brackets)'
        ),
        'indexes_added', jsonb_build_array(
            'idx_sends_msgid UNIQUE WHERE message_id IS NOT NULL',
            'idx_sends_replied WHERE replied_at IS NOT NULL'
        ),
        'trigger_added',
            'trg_link_inbound_to_send AFTER INSERT ON marketing.inbound_messages',
        'loop_prevention',
            'split-GUC: fs-origin suppresses inbound-UPDATE emit only; campaign_sends.replied_at UPDATE emits normally',
        'side_effects', jsonb_build_object(
            'campaign_sends.replied_at',
                'auto-populated from inbound_messages.received_at on first reply',
            'inbound_messages.linked_send_id',
                'auto-populated when in_reply_to matches a known outbound message_id'
        ),
        'purpose',
            'close the inbound -> outbound reply-rate metric loop'
    )
);

COMMIT;
