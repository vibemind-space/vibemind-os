-- ============================================================================
-- Marketing-Ops: bounce-classification propagation to campaign_sends
-- ============================================================================
-- Closes the inbound -> outbound bounce-rate loop.
--
-- Today:
--   * Worker C (worker_imap_sync.py) classifies inbound mails via
--     BOUNCE_HINTS regex and writes inbound_messages.is_bounce=true
--     for matching messages (mailer-daemon, "delivery failure", 5xx
--     status codes, etc.).
--   * marketing.campaign_sends has bounced_at + bounce_reason columns
--     but NO writer.
--   * Reply-linkage trigger 007 already populates
--     inbound_messages.linked_send_id when in_reply_to matches a known
--     outbound message_id (= partial unique idx_sends_msgid).
--
-- Missing bridge: when a bounce is linked to a send, the bounce-state
-- should be reflected in campaign_sends. This migration adds an AFTER
-- UPDATE trigger that catches the linked_send_id assignment AND the
-- is_bounce=true flag, then writes campaign_sends.bounced_at +
-- bounce_reason.
--
-- Trigger surface:
--   trg_propagate_bounce fires AFTER UPDATE OF linked_send_id
--   on marketing.inbound_messages. Why UPDATE-of-linked_send_id and
--   not INSERT: trigger 007 sets linked_send_id in an AFTER-INSERT
--   trigger via split-GUC. Our INSERT-trigger would fire BEFORE 007's
--   trigger had a chance (alphabetical order trg_emit < trg_link <
--   trg_propagate doesn't help -- trg_emit fires first, trg_link
--   second; AT trg_propagate_bounce time linked_send_id IS NULL on
--   the freshly-inserted row because we're an INSERT-trigger).
--
--   The clean solution: watch the UPDATE-OF linked_send_id that the
--   007-trigger performs (it's an AFTER UPDATE we own). We DON'T need
--   to fire on every UPDATE -- only when linked_send_id transitions
--   from NULL to non-NULL AND is_bounce is true. The trigger function
--   short-circuits cheaply otherwise.
--
-- Loop prevention:
--   The trigger UPDATEs campaign_sends. That fires
--   trg_emit_sync_campaign_sends (from 004) which writes a sync_outbox
--   row -- this IS what we want: the bounce-state-transition propagates
--   to the markdown vault via Worker A. We do NOT suppress this emit.
--
--   We DO need to prevent the trigger from running during the
--   reply-linkage trigger's UPDATE of inbound_messages (which fires
--   trg_emit_sync, NOT trg_propagate_bounce -- but defensively we
--   short-circuit on linked_send_id NULL anyway).
--
-- Bounce_reason source:
--   Worker C stores the bounce subject in inbound_messages.subject
--   (e.g. "Undelivered Mail Returned to Sender"). We copy that to
--   campaign_sends.bounce_reason -- it's short enough and operationally
--   the most useful single field. The full bounce body stays in
--   inbound_messages.body_text for forensic dig-ins.
--
-- Idempotency:
--   The trigger function only writes when bounced_at IS NULL on the
--   target campaign_sends row -- first bounce wins, re-runs are no-ops.
--   ALTER TABLE / CREATE FUNCTION / DROP+CREATE TRIGGER are all
--   idempotent. Backfill UPDATE catches any already-linked bounces.
--
-- Sticky-lockout safety:
--   trg_flip_investor_sent (005) watches AFTER INSERT OR UPDATE OF
--   delivered_at. We touch bounced_at and bounce_reason, NOT
--   delivered_at -- so the investor_already_sent lockout is NOT
--   touched by this trigger. Verified safe.

BEGIN;

-- ─── 1. Trigger function ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.propagate_bounce_to_send() RETURNS trigger AS $$
DECLARE
    bounce_subj text;
BEGIN
    -- Short-circuit: not a bounce, or not linked, or already-marked.
    IF NEW.is_bounce IS NOT TRUE THEN
        RETURN NEW;
    END IF;
    IF NEW.linked_send_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Truncate to fit comfortably (bounce_reason is text, no hard cap,
    -- but operationally the subject is ~150 chars max).
    bounce_subj := COALESCE(NULLIF(NEW.subject, ''), 'bounce (no subject)');
    IF length(bounce_subj) > 240 THEN
        bounce_subj := substring(bounce_subj from 1 for 240);
    END IF;

    -- First bounce wins. trg_emit_sync_campaign_sends will emit one
    -- outbox row for this UPDATE -- that's the desired bounce-rate
    -- propagation to the markdown vault.
    UPDATE marketing.campaign_sends
       SET bounced_at = COALESCE(bounced_at, NEW.received_at, now()),
           bounce_reason = COALESCE(bounce_reason, bounce_subj)
     WHERE id = NEW.linked_send_id
       AND bounced_at IS NULL;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.propagate_bounce_to_send() IS
    'Mirrors inbound bounce-state onto the originating send. Fires only '
    'when is_bounce=true AND linked_send_id is set. First bounce wins.';

-- ─── 2. Trigger on UPDATE OF linked_send_id ─────────────────────────────
-- Fires when 007s reply-linkage trigger transitions linked_send_id
-- from NULL to non-NULL. Cheap short-circuit when NEW.is_bounce is false.
DROP TRIGGER IF EXISTS trg_propagate_bounce ON marketing.inbound_messages;
CREATE TRIGGER trg_propagate_bounce
    AFTER UPDATE OF linked_send_id ON marketing.inbound_messages
    FOR EACH ROW
    WHEN (NEW.linked_send_id IS NOT NULL AND NEW.is_bounce IS TRUE)
    EXECUTE FUNCTION marketing.propagate_bounce_to_send();

-- Also fire on INSERT for rare cases where Worker C inserts a row that
-- already has linked_send_id set (cant happen today, but cheap to cover).
DROP TRIGGER IF EXISTS trg_propagate_bounce_ins ON marketing.inbound_messages;
CREATE TRIGGER trg_propagate_bounce_ins
    AFTER INSERT ON marketing.inbound_messages
    FOR EACH ROW
    WHEN (NEW.linked_send_id IS NOT NULL AND NEW.is_bounce IS TRUE)
    EXECUTE FUNCTION marketing.propagate_bounce_to_send();

-- ─── 3. Idempotent backfill ─────────────────────────────────────────────
-- Mirror any already-linked, already-classified bounces forward.
-- Bypass sync_outbox emit for the backfill (internal cleanup).
SELECT set_config('marketing.sync_origin', 'fs', true);

UPDATE marketing.campaign_sends cs
   SET bounced_at = COALESCE(cs.bounced_at, im.received_at),
       bounce_reason = COALESCE(cs.bounce_reason,
                                substring(COALESCE(NULLIF(im.subject,''),'bounce') from 1 for 240))
  FROM marketing.inbound_messages im
 WHERE im.is_bounce IS TRUE
   AND im.linked_send_id = cs.id
   AND cs.bounced_at IS NULL;

SELECT set_config('marketing.sync_origin', '', true);

-- ─── 4. Audit ───────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:009',
    'schema.add_trigger',
    'marketing.inbound_messages,marketing.campaign_sends',
    jsonb_build_object(
        'triggers_added', jsonb_build_array(
            'trg_propagate_bounce AFTER UPDATE OF linked_send_id',
            'trg_propagate_bounce_ins AFTER INSERT (edge case)'
        ),
        'function_added', 'marketing.propagate_bounce_to_send',
        'propagation_path',
            'inbound_messages.is_bounce=true + linked_send_id set -> campaign_sends.bounced_at + bounce_reason',
        'sticky_lockout_impact',
            'none -- trigger touches bounced_at + bounce_reason, NOT delivered_at',
        'purpose',
            'close the inbound -> outbound bounce-rate metric loop'
    )
);

COMMIT;
