-- ============================================================================
-- Marketing-Ops: reply_proposals -- drafts for inbound-reply approval flow
-- ============================================================================
-- Why a separate table from marketing.audience_proposals:
--   - audience_proposals is for outbound campaigns (lead-hand-generated audiences).
--     Lifecycle: pending_review -> approved -> linked to marketing.audiences.
--   - reply_proposals is for inbound replies (n8n-generated drafts).
--     Lifecycle: draft -> pending_approval -> approved/rejected -> sent.
--   - Different scope, different status-machine, different FKs.
--   - Both feed marketing.audit_log but their domain doesn't overlap.
--
-- A reply_proposal is the bridge between:
--   inbound_messages (what the recipient wrote)
--     ↓ classified as 'reply'
--     ↓ n8n enriches via Rowboat (async)
--   reply_proposals (draft for curator review)
--     ↓ curator edits + requests approval
--     ↓ OpenFang approval-card via Telegram/Discord
--   approved -> _send_paranoid (12-gate) -> Mailcow SMTP
--
-- HMAC-signed approval-token model (mirrors campaign_sends confirm-token):
--   When curator clicks "Request Approval", the marketing-API mints an
--   approval_token (HMAC over proposal_id + draft_hash + n8n_request_id).
--   OpenFang's approval-card embeds this token. When the user clicks
--   APPROVE in Telegram/Discord, OpenFang calls back with token.
--   approve-endpoint verifies token (constant-time) before send.
--   Tampering with draft body invalidates the token.
--
-- Apply:
--   docker cp 027_reply_proposals.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres \
--     -f /tmp/027_reply_proposals.sql

BEGIN;

-- ─── reply_proposals table ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.reply_proposals (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    reply_to_inbound_id     uuid        NOT NULL REFERENCES marketing.inbound_messages(id) ON DELETE CASCADE,
    proposal_type           text        NOT NULL DEFAULT 'reply',
    status                  text        NOT NULL DEFAULT 'draft',
    -- Draft content
    draft_to_email          citext      NOT NULL,
    draft_subject           text        NOT NULL,
    draft_body_text         text        NOT NULL,
    draft_body_html         text,
    draft_template_id       uuid        REFERENCES marketing.templates(id) ON DELETE SET NULL,
    -- Provenance
    created_by              text        NOT NULL,                   -- 'n8n:reply-enrichment-v1' or 'curator:felix'
    edited_by               text,                                    -- last editor (curator usually)
    edited_at               timestamptz,
    -- Rowboat async enrichment
    rowboat_request_id      text,
    rowboat_context         jsonb,
    rowboat_received_at     timestamptz,
    -- Approval flow
    approval_channel        text,                                    -- 'telegram'|'discord'|'openfang'
    approval_requested_at   timestamptz,
    approval_token_hash     text,                                    -- sha256 of HMAC-signed token (for verify-on-callback)
    approved_at             timestamptz,
    approved_by             text,
    rejected_at             timestamptz,
    rejected_by             text,
    rejection_reason        text,
    -- Send result
    sent_at                 timestamptz,
    sent_message_id         text,
    sent_via_campaign_id    uuid REFERENCES marketing.campaigns(id) ON DELETE SET NULL,
    -- Standard timestamps
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT reply_proposals_status_known CHECK (
        status IN ('draft', 'pending_approval', 'approved', 'rejected', 'sent')
    ),
    CONSTRAINT reply_proposals_proposal_type_known CHECK (
        proposal_type IN ('reply', 'unsubscribe-confirm', 'opt-out-ack')
    ),
    CONSTRAINT reply_proposals_subject_nonempty CHECK (length(draft_subject) > 0),
    CONSTRAINT reply_proposals_body_nonempty CHECK (length(draft_body_text) > 0),
    -- Audit: every state-transition leaves an actor
    CONSTRAINT reply_proposals_approved_has_actor CHECK (
        approved_at IS NULL OR approved_by IS NOT NULL
    ),
    CONSTRAINT reply_proposals_rejected_has_actor CHECK (
        rejected_at IS NULL OR rejected_by IS NOT NULL
    ),
    -- Approval token only set when approval requested
    CONSTRAINT reply_proposals_token_when_requested CHECK (
        (approval_requested_at IS NULL AND approval_token_hash IS NULL)
        OR (approval_requested_at IS NOT NULL AND approval_token_hash IS NOT NULL)
    )
);

COMMENT ON TABLE marketing.reply_proposals IS
    'Drafts for inbound-reply approval flow. n8n creates with status=draft. '
    'Curator edits via Curator-Space UI. On request_approval, marketing-API '
    'mints HMAC-signed token, stored as approval_token_hash. OpenFang sends '
    'approval-card, callback verifies token -> approved/rejected. Approved '
    'proposals send via _send_paranoid (12-gate stack).';

COMMENT ON COLUMN marketing.reply_proposals.approval_token_hash IS
    'sha256 hash of the HMAC-signed approval-token (NOT the token itself). '
    'On approve-callback, marketing-API verifies sha256(provided_token) == '
    'approval_token_hash. Constant-time compare. Single-use: cleared on '
    'approve/reject.';

COMMENT ON COLUMN marketing.reply_proposals.rowboat_context IS
    'Async-arrived RAG context from Rowboat /knowledge. n8n creates proposal '
    'with rowboat_request_id only; Rowboat callback writes context + sets '
    'rowboat_received_at. NULL means context not yet received.';

-- ─── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_reply_proposals_inbound
    ON marketing.reply_proposals (reply_to_inbound_id);

CREATE INDEX IF NOT EXISTS idx_reply_proposals_status
    ON marketing.reply_proposals (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reply_proposals_pending_approval
    ON marketing.reply_proposals (approval_requested_at DESC)
    WHERE status = 'pending_approval';

CREATE INDEX IF NOT EXISTS idx_reply_proposals_rowboat_pending
    ON marketing.reply_proposals (rowboat_request_id)
    WHERE rowboat_request_id IS NOT NULL AND rowboat_received_at IS NULL;

-- ─── updated_at trigger ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing._reply_proposals_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reply_proposals_updated_at ON marketing.reply_proposals;
CREATE TRIGGER trg_reply_proposals_updated_at
    BEFORE UPDATE ON marketing.reply_proposals
    FOR EACH ROW EXECUTE FUNCTION marketing._reply_proposals_updated_at();

-- ─── Idempotency: only ONE open proposal per inbound ──────────────────
-- Block n8n from creating duplicate proposals for the same inbound.
-- "Open" = not (rejected OR sent).
CREATE UNIQUE INDEX IF NOT EXISTS uq_reply_proposals_one_open_per_inbound
    ON marketing.reply_proposals (reply_to_inbound_id)
    WHERE status NOT IN ('rejected', 'sent');

-- ─── Emit lifecycle events ────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing._emit_reply_proposal_event() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM marketing.emit_webhook_event(
            'reply_proposal_created',
            jsonb_build_object(
                'proposal_id', NEW.id,
                'reply_to_inbound_id', NEW.reply_to_inbound_id,
                'draft_to_email', NEW.draft_to_email,
                'created_by', NEW.created_by
            ),
            NULL,
            NEW.draft_to_email
        );
    ELSIF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        PERFORM marketing.emit_webhook_event(
            'reply_proposal_status_changed',
            jsonb_build_object(
                'proposal_id', NEW.id,
                'old_status', OLD.status,
                'new_status', NEW.status,
                'approval_channel', NEW.approval_channel,
                'approved_by', NEW.approved_by,
                'rejected_by', NEW.rejected_by
            ),
            NEW.sent_via_campaign_id,
            NEW.draft_to_email
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emit_reply_proposal_event ON marketing.reply_proposals;
CREATE TRIGGER trg_emit_reply_proposal_event
    AFTER INSERT OR UPDATE ON marketing.reply_proposals
    FOR EACH ROW EXECUTE FUNCTION marketing._emit_reply_proposal_event();

-- Allow the new event kinds
ALTER TABLE marketing.webhook_events
    DROP CONSTRAINT IF EXISTS webhook_events_event_kind_check;
ALTER TABLE marketing.webhook_events
    ADD CONSTRAINT webhook_events_event_kind_check
    CHECK (event_kind IN (
        'sent', 'open', 'click', 'bounce',
        'unsubscribe', 'reply', 'send_failed',
        'campaign_status_change', 'subscription_test',
        'inbound_received', 'inbound_classified',
        'reply_proposal_created', 'reply_proposal_status_changed'
    ));

-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:027',
    'reply_proposals.table_created',
    'marketing.reply_proposals',
    jsonb_build_object(
        'note',
        'Reply-proposal table for inbound-reply approval-flow. Separate from '
        'audience_proposals (which is for outbound-campaign audience generation). '
        'Lifecycle: draft -> pending_approval -> approved/rejected -> sent. '
        'HMAC-token-based approval, audit on every state transition.',
        'events_added', jsonb_build_array(
            'reply_proposal_created', 'reply_proposal_status_changed'
        )
    )
);

COMMIT;
