-- ============================================================================
-- Schicht 7.0a — broadcast_proposals: approval-gated outbound posts
-- ============================================================================
-- Mirrors marketing.reply_proposals (Schicht 6.5) but for outbound
-- broadcasts: posts to LinkedIn, Mastodon, Reddit, Discord-channel, etc.
-- where the channel is NOT email (those go through campaigns + _send_paranoid).
--
-- Why separate from reply_proposals:
--   - reply_proposals: triggered by inbound, reply to specific person
--     (draft_to_email, reply_to_inbound_id)
--   - broadcast_proposals: standalone outbound to social/channel
--     (no inbound reference, no specific recipient — channel-level)
--   Different lifecycle, different audit needs, different curator-UI views.
--
-- Why approval-gated at the DB-level (not just UI):
--   Defense in depth. Even if the n8n workflow gets re-imported / webhook
--   gets pinged directly, the approve-call must verify an HMAC-signed token
--   that was minted by marketing-API on user-explicit "request approval"
--   click. Same model as reply_proposals.
--
-- Lifecycle:
--   draft -> pending_approval -> approved -> sent
--                             -> rejected
--
-- Apply:
--   docker cp 030_broadcast_proposals.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/030_broadcast_proposals.sql

BEGIN;

CREATE TABLE IF NOT EXISTS marketing.broadcast_proposals (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    channel                 text        NOT NULL REFERENCES marketing.channel_config(channel),
    status                  text        NOT NULL DEFAULT 'draft',
    -- Draft content
    draft_subject           text,                                    -- optional, mostly for documentation
    draft_body_text         text        NOT NULL,
    draft_body_html         text,                                    -- only used for channels that support it
    draft_media_url         text,                                    -- optional image/video for the broadcast
    draft_template_id       uuid        REFERENCES marketing.templates(id) ON DELETE SET NULL,
    draft_channel_params    jsonb       DEFAULT '{}'::jsonb,         -- channel-specific overrides (subreddit, hashtags, parse_mode, ...)
    -- Provenance
    created_by              text        NOT NULL,
    edited_by               text,
    edited_at               timestamptz,
    -- Approval flow (mirrors reply_proposals from Schicht 6.5)
    approval_channel        text,                                    -- 'telegram'|'discord'|'openfang'
    approval_requested_at   timestamptz,
    approval_token_hash     text,
    approved_at             timestamptz,
    approved_by             text,
    rejected_at             timestamptz,
    rejected_by             text,
    rejection_reason        text,
    -- Send result
    sent_at                 timestamptz,
    sent_external_id        text,                                    -- e.g. 'urn:li:share:7470191378061438978' for LinkedIn
    sent_via_campaign_id    uuid REFERENCES marketing.campaigns(id) ON DELETE SET NULL,
    -- Standard timestamps
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT broadcast_proposals_status_known CHECK (
        status IN ('draft', 'pending_approval', 'approved', 'rejected', 'sent', 'failed')
    ),
    CONSTRAINT broadcast_proposals_body_nonempty CHECK (length(draft_body_text) > 0),
    -- Audit: every state-transition leaves an actor
    CONSTRAINT broadcast_proposals_approved_has_actor CHECK (
        approved_at IS NULL OR approved_by IS NOT NULL
    ),
    CONSTRAINT broadcast_proposals_rejected_has_actor CHECK (
        rejected_at IS NULL OR rejected_by IS NOT NULL
    ),
    -- Approval token only set when approval requested
    CONSTRAINT broadcast_proposals_token_when_requested CHECK (
        (approval_requested_at IS NULL AND approval_token_hash IS NULL)
        OR (approval_requested_at IS NOT NULL AND approval_token_hash IS NOT NULL)
    )
);

COMMENT ON TABLE marketing.broadcast_proposals IS
    'Approval-gated outbound broadcasts to social/channels (LinkedIn, Mastodon, Reddit, Discord-channel, ...). '
    'Curator drafts -> requests approval -> OpenFang sends approval-card -> human approves with HMAC token -> '
    'n8n workflow verifies token via marketing-API and posts. Mirrors reply_proposals (Schicht 6.5) but for '
    'outbound (no inbound trigger, no specific recipient).';

COMMENT ON COLUMN marketing.broadcast_proposals.approval_token_hash IS
    'sha256 hash of the HMAC-signed approval-token (NOT the token itself). On approve-callback, marketing-API '
    'verifies sha256(provided_token) == approval_token_hash. Constant-time compare. Single-use: cleared on '
    'approve/reject. Same model as reply_proposals.';

COMMENT ON COLUMN marketing.broadcast_proposals.draft_channel_params IS
    'Channel-specific params (e.g. {"subreddit": "r/test"} for reddit, {"parse_mode": "MarkdownV2"} for '
    'telegram, {"visibility": "PUBLIC"} for linkedin). Validated by the channel-specific sender at send-time.';

COMMENT ON COLUMN marketing.broadcast_proposals.sent_external_id IS
    'Platform-specific post-id returned after successful send. For LinkedIn: "urn:li:share:XXX". For Mastodon: '
    'status-id. For Discord: message-id. Stored verbatim for later reference / delete-from-platform actions.';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_broadcast_proposals_status
    ON marketing.broadcast_proposals (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_broadcast_proposals_pending_approval
    ON marketing.broadcast_proposals (approval_requested_at DESC)
    WHERE status = 'pending_approval';

CREATE INDEX IF NOT EXISTS idx_broadcast_proposals_channel
    ON marketing.broadcast_proposals (channel, created_at DESC);

-- updated_at trigger
CREATE OR REPLACE FUNCTION marketing._broadcast_proposals_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_broadcast_proposals_updated_at ON marketing.broadcast_proposals;
CREATE TRIGGER trg_broadcast_proposals_updated_at
    BEFORE UPDATE ON marketing.broadcast_proposals
    FOR EACH ROW EXECUTE FUNCTION marketing._broadcast_proposals_updated_at();

-- Emit lifecycle events
CREATE OR REPLACE FUNCTION marketing._emit_broadcast_proposal_event() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM marketing.emit_webhook_event(
            'broadcast_proposal_created',
            jsonb_build_object(
                'proposal_id', NEW.id,
                'channel', NEW.channel,
                'created_by', NEW.created_by
            ),
            NULL,
            NULL
        );
    ELSIF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        PERFORM marketing.emit_webhook_event(
            'broadcast_proposal_status_changed',
            jsonb_build_object(
                'proposal_id', NEW.id,
                'channel', NEW.channel,
                'old_status', OLD.status,
                'new_status', NEW.status,
                'approval_channel', NEW.approval_channel,
                'approved_by', NEW.approved_by,
                'rejected_by', NEW.rejected_by
            ),
            NULL,
            NULL
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emit_broadcast_proposal_event ON marketing.broadcast_proposals;
CREATE TRIGGER trg_emit_broadcast_proposal_event
    AFTER INSERT OR UPDATE ON marketing.broadcast_proposals
    FOR EACH ROW EXECUTE FUNCTION marketing._emit_broadcast_proposal_event();

-- Allow the new event kinds in the CHECK constraint
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
        -- Schicht 7.0a:
        'broadcast_proposal_created', 'broadcast_proposal_status_changed'
    ));

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:030',
    'broadcast_proposals.table_created',
    'marketing.broadcast_proposals',
    jsonb_build_object(
        'note',
        'Approval-gated outbound broadcasts. Mirrors reply_proposals (Schicht 6.5) lifecycle. '
        'Curator UI (Schicht 7.0b) creates drafts; n8n workflow refuses to post without verified token.',
        'events_added', jsonb_build_array(
            'broadcast_proposal_created', 'broadcast_proposal_status_changed'
        )
    )
);

COMMIT;
