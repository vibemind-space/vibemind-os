-- ============================================================================
-- Schicht 8.0c — Channel-aware webhook routing (one n8n workflow per channel)
-- ============================================================================
-- Plan: spaces/marketing/docs/2026-07-02-bubble-auto-dispatch-plan.md (Phase 4)
--
-- Design decision: one ISOLATED n8n workflow per channel, no IF-filter inside
-- the workflows. Routing happens in the webhook bus:
--
--   (a) new event kind `broadcast_approved` — emitted exactly when a
--       broadcast_proposal transitions to status='approved'. Payload carries
--       everything the channel workflow needs to post (body text, subject,
--       media, channel params) so n8n never has to query back.
--   (b) webhook_subscriptions.channel_filter — a subscription can bind to
--       ONE channel; the delivery worker only fans out events whose
--       payload.channel matches (NULL = no filter, old behaviour).
--   (c) per-channel seed subscriptions pointing at
--       http://127.0.0.1:15678/webhook/marketing-<channel>-broadcast
--       — seeded ACTIVE=false. Activation happens when the matching n8n
--       workflow is imported (n8n_workflows/import.ps1), otherwise every
--       approval would pile up 404-deliveries against a missing webhook.
--
-- The generic `broadcast_proposal_status_changed` event keeps firing
-- unchanged (audit/monitoring consumers).
--
-- Apply:
--   docker cp 038_channel_aware_webhook_routing.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/038_channel_aware_webhook_routing.sql

BEGIN;

-- ─── (b) channel filter on subscriptions ───────────────────────────────────

ALTER TABLE marketing.webhook_subscriptions
    ADD COLUMN IF NOT EXISTS channel_filter text;

COMMENT ON COLUMN marketing.webhook_subscriptions.channel_filter IS
    'Schicht 8.0c: bind subscription to ONE channel. Delivery worker only '
    'fans out events whose payload->>''channel'' equals this. NULL = match '
    'all channels (pre-038 behaviour).';

-- ─── (a) broadcast_approved event kind ──────────────────────────────────────

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
        'broadcast_proposal_created', 'broadcast_proposal_status_changed',
        -- Schicht 8.0c:
        'broadcast_approved'
    ));

-- Extend the emitter: on transition to 'approved' additionally emit the
-- send-ready event with full draft content.
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
        -- Schicht 8.0c: send-ready event for the per-channel n8n workflow.
        -- Full draft content inline so the workflow posts without a
        -- query-back. bubble_id lets the workflow report back per bubble.
        IF NEW.status = 'approved' THEN
            PERFORM marketing.emit_webhook_event(
                'broadcast_approved',
                jsonb_build_object(
                    'proposal_id', NEW.id,
                    'channel', NEW.channel,
                    'bubble_id', NEW.bubble_id,
                    'body_text', NEW.draft_body_text,
                    'subject', NEW.draft_subject,
                    'body_html', NEW.draft_body_html,
                    'media_url', NEW.draft_media_url,
                    'channel_params', NEW.draft_channel_params,
                    'approved_by', NEW.approved_by,
                    'approved_at', NEW.approved_at
                ),
                NULL,
                NULL
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─── (c) per-channel seed subscriptions (inactive until workflow import) ────

INSERT INTO marketing.webhook_subscriptions
    (name, url, events, secret, active, channel_filter)
SELECT
    'n8n-' || ch || '-broadcast',
    'http://127.0.0.1:15678/webhook/marketing-' || ch || '-broadcast',
    ARRAY['broadcast_approved'],
    encode(gen_random_bytes(24), 'hex'),
    false,   -- activated by n8n_workflows/import.ps1 once the workflow exists
    ch
FROM unnest(ARRAY['linkedin', 'x', 'email', 'discord', 'telegram']) AS ch
WHERE NOT EXISTS (
    SELECT 1 FROM marketing.webhook_subscriptions s
    WHERE s.name = 'n8n-' || ch || '-broadcast'
);

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:038',
    'channel_aware_webhook_routing.added',
    'marketing.webhook_subscriptions',
    jsonb_build_object(
        'new_event_kind', 'broadcast_approved',
        'new_column', 'webhook_subscriptions.channel_filter',
        'seeded_channels', jsonb_build_array(
            'linkedin', 'x', 'email', 'discord', 'telegram'
        ),
        'seeds_active', false
    )
);

COMMIT;
