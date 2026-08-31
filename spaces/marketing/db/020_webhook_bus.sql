-- ============================================================================
-- Marketing-Ops: webhook-bus foundation (Schicht 5.3)
-- ============================================================================
-- Brevo-equivalent lifecycle event delivery to external HTTP endpoints.
--
-- Two-table model:
--   1. webhook_subscriptions — operator-registered HTTP receivers with their
--      event filter and signing secret.
--   2. webhook_events        — append-only log of marketing lifecycle events
--      (sent / open / click / bounce / unsubscribe / reply / open_test).
--      Workers/triggers INSERT here; webhook_delivery worker drains and
--      fans out to all matching subscriptions.
--
-- Why dedicated tables (not reusing sync_outbox from 004):
--   sync_outbox is the DB↔FS markdown vault sync log. Its rows carry full
--   table snapshots and are drained by Worker A → Markdown writer. Putting
--   external-webhook events on the same table would couple the consent-vault
--   sync to outbound HTTP — sync would block on webhook receiver failures,
--   and a noisy webhook subscription would slow down vault writes. Separate
--   tables = separate failure domains.
--
-- Signing model (HMAC-SHA256):
--   Each subscription has its own `secret`. Payload sent as JSON body.
--   Header: X-Vibemind-Signature: sha256=<hex hmac of raw body bytes>
--   Header: X-Vibemind-Event:     <event_kind>
--   Header: X-Vibemind-Event-Id:  <webhook_events.id>
--   Header: X-Vibemind-Timestamp: <epoch seconds>
--   Receivers verify by HMAC-SHA256(secret, raw_body) — same model as
--   GitHub webhooks. Constant-time compare on the receiver side.
--
-- Retry contract:
--   2xx       → mark delivered, increment subscription.last_success
--   4xx       → mark delivered (permanent fail), increment failure_count
--   5xx / net → leave delivered_at NULL, increment retry_count, retry with
--               exponential backoff (1m, 5m, 15m, 1h, 4h, then dead)
--   50 consecutive failures → auto-disable subscription, alert via audit_log
--
-- Apply:
--   docker cp 020_webhook_bus.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/020_webhook_bus.sql

BEGIN;

-- ─── webhook_subscriptions ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.webhook_subscriptions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text        NOT NULL,
    url             text        NOT NULL,
    events          text[]      NOT NULL,
    secret          text        NOT NULL,
    active          boolean     NOT NULL DEFAULT true,
    failure_count   int         NOT NULL DEFAULT 0,
    success_count   int         NOT NULL DEFAULT 0,
    last_success_at timestamptz,
    last_failure_at timestamptz,
    last_error      text,
    disabled_at     timestamptz,
    disabled_reason text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- url must be http(s); the worker also validates at runtime
    CHECK (url ~* '^https?://'),
    -- secret must be at least 32 chars (HMAC sanity)
    CHECK (length(secret) >= 32),
    -- name unique per active subscription
    CHECK (length(name) BETWEEN 1 AND 200)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_subscriptions_name_active
    ON marketing.webhook_subscriptions (name)
    WHERE active = true;

CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_active
    ON marketing.webhook_subscriptions (active)
    WHERE active = true;

COMMENT ON TABLE marketing.webhook_subscriptions IS
    'Operator-registered HTTP endpoints that receive marketing lifecycle events. '
    'Each subscription has its own HMAC-SHA256 secret. The webhook_delivery '
    'worker fans events out to every active subscription whose events array '
    'contains the event_kind.';

COMMENT ON COLUMN marketing.webhook_subscriptions.events IS
    'Array of event kinds this subscription wants. Known kinds: '
    'sent, open, click, bounce, unsubscribe, reply, send_failed. '
    'Use [''*''] to subscribe to all events.';

COMMENT ON COLUMN marketing.webhook_subscriptions.secret IS
    'HMAC-SHA256 key. Worker signs raw body with this key and sends hex '
    'digest in X-Vibemind-Signature: sha256=<hex> header. NEVER logged in '
    'audit_log payloads — only its prefix.';


-- ─── webhook_events (append-only log) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.webhook_events (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_kind      text        NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    payload         jsonb       NOT NULL,
    -- Optional dimensional fields for filtering / debugging (also in payload)
    campaign_id     uuid        REFERENCES marketing.campaigns(id) ON DELETE SET NULL,
    email           citext,
    -- Delivery bookkeeping (per-event, not per-subscription — that's webhook_deliveries)
    fanned_out_at   timestamptz,
    fanout_count    int         NOT NULL DEFAULT 0,

    CHECK (event_kind IN (
        'sent', 'open', 'click', 'bounce',
        'unsubscribe', 'reply', 'send_failed',
        'campaign_status_change', 'subscription_test'
    ))
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_unfanned
    ON marketing.webhook_events (occurred_at)
    WHERE fanned_out_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_events_campaign
    ON marketing.webhook_events (campaign_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_events_kind_time
    ON marketing.webhook_events (event_kind, occurred_at DESC);

COMMENT ON TABLE marketing.webhook_events IS
    'Append-only lifecycle event log. webhook_delivery worker drains rows '
    'where fanned_out_at IS NULL and writes one row per (event, subscription) '
    'into webhook_deliveries.';


-- ─── webhook_deliveries (per-event-per-subscription) ──────────────────
CREATE TABLE IF NOT EXISTS marketing.webhook_deliveries (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        uuid        NOT NULL REFERENCES marketing.webhook_events(id) ON DELETE CASCADE,
    subscription_id uuid        NOT NULL REFERENCES marketing.webhook_subscriptions(id) ON DELETE CASCADE,
    attempted_at    timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz,
    retry_count     int         NOT NULL DEFAULT 0,
    next_retry_at   timestamptz,
    http_status     int,
    response_body   text,            -- truncated to 1000 chars by the worker
    error           text,            -- transport-error if no HTTP response
    dead            boolean     NOT NULL DEFAULT false,
    UNIQUE (event_id, subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending
    ON marketing.webhook_deliveries (next_retry_at)
    WHERE delivered_at IS NULL AND dead = false;

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_subscription
    ON marketing.webhook_deliveries (subscription_id, attempted_at DESC);

COMMENT ON TABLE marketing.webhook_deliveries IS
    'Per-event-per-subscription delivery tracking. UNIQUE (event_id, sub_id) '
    'is the atomic claim primitive: a parallel worker cannot double-deliver. '
    'Worker drains rows where delivered_at IS NULL AND dead = false AND '
    'next_retry_at <= now().';


-- ─── Convenience: emit_webhook_event() helper ─────────────────────────
-- Single entry-point used by triggers + workers. Atomic INSERT, returns
-- the new event_id. Triggers stay narrow (one CALL per event).
CREATE OR REPLACE FUNCTION marketing.emit_webhook_event(
    p_event_kind  text,
    p_payload     jsonb,
    p_campaign_id uuid    DEFAULT NULL,
    p_email       citext  DEFAULT NULL
) RETURNS uuid AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO marketing.webhook_events
        (event_kind, payload, campaign_id, email)
    VALUES
        (p_event_kind, p_payload, p_campaign_id, p_email)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.emit_webhook_event IS
    'Single entry-point for emitting webhook events. Triggers and workers '
    'call this once per lifecycle change. The webhook_delivery worker drains '
    'webhook_events and fans out to subscriptions.';


-- ─── updated_at trigger on webhook_subscriptions ─────────────────────
CREATE OR REPLACE FUNCTION marketing._webhook_subscriptions_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_webhook_subscriptions_updated_at
    ON marketing.webhook_subscriptions;
CREATE TRIGGER trg_webhook_subscriptions_updated_at
    BEFORE UPDATE ON marketing.webhook_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION marketing._webhook_subscriptions_updated_at();


-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:020',
    'webhook_bus.schema_created',
    'marketing.webhook_subscriptions',
    jsonb_build_object(
        'tables', jsonb_build_array(
            'marketing.webhook_subscriptions',
            'marketing.webhook_events',
            'marketing.webhook_deliveries'
        ),
        'helper', 'marketing.emit_webhook_event(kind, payload, campaign_id?, email?)',
        'note', 'No event-emit triggers yet. _send_paranoid and lifecycle workers '
                'wire emit_webhook_event() in their own commits.'
    )
);

COMMIT;
