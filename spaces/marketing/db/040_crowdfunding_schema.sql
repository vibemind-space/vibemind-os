-- ============================================================================
-- Schicht 8.1 — Crowdfunding: batches + contributions ledger + events + view
-- ============================================================================
-- Plan: spaces/marketing/docs/2026-07-02-bubble-auto-dispatch-plan.md (Phase 6)
--
-- Mirrors the broadcast_proposals pattern for Multi-Recipient payment
-- campaigns: 1 batch per (bubble, channel), approval-gated via the same
-- HMAC + OpenFang mechanics; per recipient one ledger row with a unique
-- PayPal order/approve_url (created via VibeMind-OS/payment-infra SDK).
--
-- Hard rules (mirror AGENTS.md):
--   * contributions.paid_at has EXACTLY ONE writer: the
--     paypal_webhook_handler worker (gate G12). batch_sender NEVER
--     touches it.
--   * amounts live on the BATCH (server-side), never per-request.
--
-- Consolidates planned 040-043 into one file (batches/ledger/events/view).
--
-- Apply:
--   docker cp 040_crowdfunding_schema.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/040_crowdfunding_schema.sql

BEGIN;

-- ─── batches (analog broadcast_proposals) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS marketing.crowdfunding_batches (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bubble_id               text        REFERENCES public.ideas(id) ON DELETE SET NULL,
    channel                 text        NOT NULL,   -- email | linkedin-dm | x-dm | ...
    status                  text        NOT NULL DEFAULT 'draft',
    -- Money (server-side, EUR by default — cross-currency stalls DE buyers)
    amount                  text        NOT NULL DEFAULT '1.00',
    currency                text        NOT NULL DEFAULT 'EUR',
    -- Recipients
    recipients_audience_id  uuid        REFERENCES marketing.audiences(id) ON DELETE SET NULL,
    -- Message template context (V1: bubble description; Template-Skill later)
    message_template        text,
    -- Approval flow (mirrors broadcast_proposals / Schicht 7.0)
    approval_channel        text,
    approval_requested_at   timestamptz,
    approval_token_hash     text,
    approval_token_raw      text,
    openfang_approval_id    uuid,
    approved_at             timestamptz,
    approved_by             text,
    rejected_at             timestamptz,
    rejected_by             text,
    rejection_reason        text,
    -- Send result
    sent_at                 timestamptz,
    sent_batch_size         int,
    created_by              text        NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT crowdfunding_batches_status_known CHECK (
        status IN ('draft', 'pending_approval', 'approved',
                   'rejected', 'sent', 'failed')
    ),
    CONSTRAINT crowdfunding_batches_approved_has_actor CHECK (
        approved_at IS NULL OR approved_by IS NOT NULL
    ),
    CONSTRAINT crowdfunding_batches_rejected_has_actor CHECK (
        rejected_at IS NULL OR rejected_by IS NOT NULL
    ),
    CONSTRAINT crowdfunding_batches_amount_sane CHECK (
        amount ~ '^[0-9]+\.[0-9]{2}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_crowdfunding_batches_status
    ON marketing.crowdfunding_batches (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_crowdfunding_batches_bubble
    ON marketing.crowdfunding_batches (bubble_id)
    WHERE bubble_id IS NOT NULL;

CREATE OR REPLACE FUNCTION marketing._crowdfunding_batches_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_crowdfunding_batches_updated_at
    ON marketing.crowdfunding_batches;
CREATE TRIGGER trg_crowdfunding_batches_updated_at
    BEFORE UPDATE ON marketing.crowdfunding_batches
    FOR EACH ROW EXECUTE FUNCTION marketing._crowdfunding_batches_updated_at();

-- ─── contributions ledger (1 row per recipient) ─────────────────────────────

CREATE TABLE IF NOT EXISTS marketing.crowdfunding_contributions (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id            uuid        NOT NULL
                        REFERENCES marketing.crowdfunding_batches(id) ON DELETE CASCADE,
    recipient_id        text        NOT NULL,
    recipient_name      text,
    -- Payment (via payment-infra; order created lazily by batch_sender)
    order_id            text        UNIQUE,
    approve_url         text,
    amount              text        NOT NULL,
    currency            text        NOT NULL,
    status              text        NOT NULL DEFAULT 'created',
    created_at          timestamptz NOT NULL DEFAULT now(),
    sent_at             timestamptz,        -- outreach message went out
    paid_at             timestamptz,        -- G12: ONLY paypal_webhook_handler writes
    capture_id          text,
    payment_metadata    jsonb       DEFAULT '{}'::jsonb,

    CONSTRAINT crowdfunding_contributions_status_known CHECK (
        status IN ('created', 'sent', 'paid', 'failed')
    ),
    -- Idempotency: one link per (batch, recipient) — the G7/G11 gate
    CONSTRAINT crowdfunding_contributions_unique_recipient
        UNIQUE (batch_id, recipient_id)
);

CREATE INDEX IF NOT EXISTS idx_crowdfunding_contributions_batch
    ON marketing.crowdfunding_contributions (batch_id, status);
CREATE INDEX IF NOT EXISTS idx_crowdfunding_contributions_unpaid
    ON marketing.crowdfunding_contributions (order_id)
    WHERE paid_at IS NULL AND order_id IS NOT NULL;

COMMENT ON COLUMN marketing.crowdfunding_contributions.paid_at IS
    'Gate G12: exactly ONE writer — workers/paypal_webhook_handler '
    '(verified provider webhook or explicit status-poll reconcile). '
    'batch_sender NEVER sets this.';

-- ─── webhook events for the bus ─────────────────────────────────────────────

ALTER TABLE marketing.webhook_events
    DROP CONSTRAINT IF EXISTS webhook_events_event_kind_check;
ALTER TABLE marketing.webhook_events
    ADD CONSTRAINT webhook_events_event_kind_check
    CHECK (event_kind IN (
        'sent', 'open', 'click', 'bounce',
        'unsubscribe', 'reply', 'send_failed',
        'campaign_status_change', 'subscription_test',
        'inbound_received', 'inbound_classified',
        'reply_proposal_created', 'reply_proposal_status_changed',
        'broadcast_proposal_created', 'broadcast_proposal_status_changed',
        'broadcast_approved',
        -- Schicht 8.1:
        'crowdfunding_batch_status_changed', 'crowdfunding_approved',
        'contribution_paid'
    ));

CREATE OR REPLACE FUNCTION marketing._emit_crowdfunding_batch_event() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        PERFORM marketing.emit_webhook_event(
            'crowdfunding_batch_status_changed',
            jsonb_build_object(
                'batch_id', NEW.id,
                'channel', NEW.channel,
                'bubble_id', NEW.bubble_id,
                'old_status', OLD.status,
                'new_status', NEW.status
            ),
            NULL, NULL
        );
        IF NEW.status = 'approved' THEN
            -- send-ready: the per-channel crowdfunding n8n workflow picks
            -- this up and triggers batch_sender via the marketing-API.
            PERFORM marketing.emit_webhook_event(
                'crowdfunding_approved',
                jsonb_build_object(
                    'batch_id', NEW.id,
                    'channel', NEW.channel,
                    'bubble_id', NEW.bubble_id,
                    'amount', NEW.amount,
                    'currency', NEW.currency,
                    'approved_by', NEW.approved_by
                ),
                NULL, NULL
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emit_crowdfunding_batch_event
    ON marketing.crowdfunding_batches;
CREATE TRIGGER trg_emit_crowdfunding_batch_event
    AFTER UPDATE ON marketing.crowdfunding_batches
    FOR EACH ROW EXECUTE FUNCTION marketing._emit_crowdfunding_batch_event();

-- ─── pipeline view (analog v_bubble_pipeline / 035) ─────────────────────────

CREATE OR REPLACE VIEW marketing.v_crowdfunding_pipeline AS
SELECT
    b.id                          AS batch_id,
    b.bubble_id,
    b.channel,
    b.status                      AS batch_status,
    b.amount, b.currency,
    b.created_at, b.sent_at,
    count(c.id)                   AS recipients,
    count(c.id) FILTER (WHERE c.status = 'created') AS links_created,
    count(c.id) FILTER (WHERE c.status = 'sent')    AS messages_sent,
    count(c.id) FILTER (WHERE c.paid_at IS NOT NULL) AS paid,
    count(c.id) FILTER (WHERE c.status = 'failed')  AS failed
FROM marketing.crowdfunding_batches b
LEFT JOIN marketing.crowdfunding_contributions c ON c.batch_id = b.id
GROUP BY b.id;

COMMENT ON VIEW marketing.v_crowdfunding_pipeline IS
    'Schicht 8.1: one row per crowdfunding batch with contribution '
    'funnel counts (links_created -> messages_sent -> paid).';

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:040',
    'crowdfunding_schema.created',
    'marketing.crowdfunding_batches',
    jsonb_build_object(
        'tables', jsonb_build_array(
            'crowdfunding_batches', 'crowdfunding_contributions'),
        'view', 'v_crowdfunding_pipeline',
        'events_added', jsonb_build_array(
            'crowdfunding_batch_status_changed', 'crowdfunding_approved',
            'contribution_paid'),
        'g12_rule', 'paid_at single-writer = paypal_webhook_handler'
    )
);

COMMIT;
