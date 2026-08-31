-- ============================================================================
-- Marketing-Ops: inbound classification + pre-tagging (Schicht 6.1)
-- ============================================================================
-- Extends marketing.inbound_messages to support the two-stage classification
-- model from Schicht 6 spec:
--
--   pre_classification   -- written by Worker C at INSERT-time via deterministic
--                          regex-rules (DSN-bounces, List-Unsubscribe headers,
--                          In-Reply-To, spam-score). Cheap, fast, audit-clear.
--                          Existing is_bounce/is_autoreply booleans subsume into
--                          this string column (more expressive, future-proof).
--
--   classification        -- final classification, can be overridden by n8n
--                          (regex-fallback + LLM) or curator (human review).
--                          Precedence: curator > n8n > pre_classification.
--
--   needs_review          -- false when pre_classification is high-confidence
--                          (bounce/opt-out). n8n skips these. True for everything
--                          else so n8n picks them up.
--
-- Existing is_bounce / is_autoreply columns kept for backwards-compat. A
-- trigger keeps them in sync with pre_classification so consumers that read
-- the booleans don't break.
--
-- Apply:
--   docker cp 026_inbound_classification.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres \
--     -f /tmp/026_inbound_classification.sql

BEGIN;

-- ─── New columns ───────────────────────────────────────────────────────
ALTER TABLE marketing.inbound_messages
    ADD COLUMN IF NOT EXISTS pre_classification        text,
    ADD COLUMN IF NOT EXISTS pre_classified_by         text,
    ADD COLUMN IF NOT EXISTS pre_classified_at         timestamptz,
    ADD COLUMN IF NOT EXISTS classification            text,
    ADD COLUMN IF NOT EXISTS classified_by             text,
    ADD COLUMN IF NOT EXISTS classified_at             timestamptz,
    ADD COLUMN IF NOT EXISTS classification_confidence real,
    ADD COLUMN IF NOT EXISTS needs_review              boolean NOT NULL DEFAULT true;

-- Known classification values. CHECK constraint added separately so we can
-- name it for later drop-and-replace if we extend the value set.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'inbound_classification_known_values'
    ) THEN
        ALTER TABLE marketing.inbound_messages
            ADD CONSTRAINT inbound_classification_known_values
            CHECK (
                classification IS NULL
                OR classification IN ('bounce','opt-out','reply','spam','question','other')
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'inbound_pre_classification_known_values'
    ) THEN
        ALTER TABLE marketing.inbound_messages
            ADD CONSTRAINT inbound_pre_classification_known_values
            CHECK (
                pre_classification IS NULL
                OR pre_classification IN ('bounce','opt-out','reply','spam','unknown')
            );
    END IF;
    -- Final classification must carry actor for audit
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'inbound_classification_audit'
    ) THEN
        ALTER TABLE marketing.inbound_messages
            ADD CONSTRAINT inbound_classification_audit
            CHECK (classification IS NULL OR classified_by IS NOT NULL);
    END IF;
END$$;

COMMENT ON COLUMN marketing.inbound_messages.pre_classification IS
    'Deterministic classification by Worker C at INSERT. Cheap regex-rules: '
    'DSN-bounces (RFC 3464), List-Unsubscribe-Post, In-Reply-To+match, '
    'X-Spam-Score, SPF/DKIM-fail. Not authoritative -- can be overridden by n8n/curator.';

COMMENT ON COLUMN marketing.inbound_messages.classification IS
    'Final classification. Precedence: curator > n8n > pre_classification. '
    'A NULL classification + needs_review=true means the message is waiting '
    'for n8n or curator review.';

COMMENT ON COLUMN marketing.inbound_messages.needs_review IS
    'False when pre_classification is high-confidence (bounce, opt-out). '
    'True for everything else -- n8n picks these up via webhook subscription.';

-- ─── Sync is_bounce/is_autoreply with pre_classification ─────────────
-- Keeps legacy boolean columns alive for any consumer that already reads them.
-- Direction: pre_classification → is_bounce/is_autoreply (one-way).
CREATE OR REPLACE FUNCTION marketing._inbound_sync_legacy_flags() RETURNS trigger AS $$
BEGIN
    IF NEW.pre_classification = 'bounce' THEN
        NEW.is_bounce := true;
    ELSIF NEW.pre_classification IS NOT NULL AND NEW.pre_classification != 'bounce' THEN
        -- Don't false-out pre-existing is_bounce that wasn't from pre_classification
        IF OLD.pre_classification IS DISTINCT FROM NEW.pre_classification THEN
            NEW.is_bounce := false;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inbound_sync_legacy_flags ON marketing.inbound_messages;
CREATE TRIGGER trg_inbound_sync_legacy_flags
    BEFORE INSERT OR UPDATE OF pre_classification ON marketing.inbound_messages
    FOR EACH ROW EXECUTE FUNCTION marketing._inbound_sync_legacy_flags();

-- ─── Emit webhook event on classification change ─────────────────────
-- When n8n or curator writes classification, emit 'inbound_classified' so
-- downstream workflows (Reply-Enrichment, audit-dashboard) can react.
CREATE OR REPLACE FUNCTION marketing._emit_inbound_classified() RETURNS trigger AS $$
BEGIN
    IF NEW.classification IS DISTINCT FROM OLD.classification
       AND NEW.classification IS NOT NULL THEN
        PERFORM marketing.emit_webhook_event(
            'inbound_classified',
            jsonb_build_object(
                'inbound_id', NEW.id,
                'from_email', NEW.from_email,
                'subject', NEW.subject,
                'classification', NEW.classification,
                'classified_by', NEW.classified_by,
                'pre_classification', NEW.pre_classification,
                'confidence', NEW.classification_confidence
            ),
            NULL,
            NEW.from_email::citext
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emit_inbound_classified ON marketing.inbound_messages;
CREATE TRIGGER trg_emit_inbound_classified
    AFTER UPDATE OF classification ON marketing.inbound_messages
    FOR EACH ROW EXECUTE FUNCTION marketing._emit_inbound_classified();

-- Webhook events needs to know 'inbound_classified' as a valid kind
ALTER TABLE marketing.webhook_events
    DROP CONSTRAINT IF EXISTS webhook_events_event_kind_check;
ALTER TABLE marketing.webhook_events
    ADD CONSTRAINT webhook_events_event_kind_check
    CHECK (event_kind IN (
        'sent', 'open', 'click', 'bounce',
        'unsubscribe', 'reply', 'send_failed',
        'campaign_status_change', 'subscription_test',
        'inbound_received', 'inbound_classified'
    ));

-- ─── Emit webhook on INSERT too ───────────────────────────────────────
-- So Worker C's INSERT (with pre_classification) is visible to n8n.
CREATE OR REPLACE FUNCTION marketing._emit_inbound_received() RETURNS trigger AS $$
BEGIN
    PERFORM marketing.emit_webhook_event(
        'inbound_received',
        jsonb_build_object(
            'inbound_id', NEW.id,
            'from_email', NEW.from_email,
            'subject', NEW.subject,
            'pre_classification', NEW.pre_classification,
            'needs_review', NEW.needs_review,
            'mailbox', NEW.mailbox
        ),
        NULL,
        NEW.from_email::citext
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emit_inbound_received ON marketing.inbound_messages;
CREATE TRIGGER trg_emit_inbound_received
    AFTER INSERT ON marketing.inbound_messages
    FOR EACH ROW EXECUTE FUNCTION marketing._emit_inbound_received();

-- ─── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_inbound_needs_review
    ON marketing.inbound_messages (received_at)
    WHERE needs_review = true AND classification IS NULL;

CREATE INDEX IF NOT EXISTS idx_inbound_pre_class
    ON marketing.inbound_messages (pre_classification, received_at);

CREATE INDEX IF NOT EXISTS idx_inbound_final_class
    ON marketing.inbound_messages (classification, received_at)
    WHERE classification IS NOT NULL;

-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:026',
    'inbound_classification.schema_extended',
    'marketing.inbound_messages',
    jsonb_build_object(
        'columns_added', jsonb_build_array(
            'pre_classification', 'pre_classified_by', 'pre_classified_at',
            'classification', 'classified_by', 'classified_at',
            'classification_confidence', 'needs_review'
        ),
        'triggers_added', jsonb_build_array(
            'trg_inbound_sync_legacy_flags',
            'trg_emit_inbound_classified',
            'trg_emit_inbound_received'
        ),
        'webhook_events_added', jsonb_build_array(
            'inbound_received', 'inbound_classified'
        ),
        'note',
        'Worker C extension writes pre_classification on INSERT. n8n + Curator '
        'override via classification column. Legacy is_bounce/is_autoreply '
        'kept in sync via _inbound_sync_legacy_flags trigger.'
    )
);

COMMIT;
