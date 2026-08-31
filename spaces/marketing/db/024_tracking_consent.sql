-- ============================================================================
-- Marketing-Ops: DSGVO tracking-consent gate
-- ============================================================================
-- Open- and click-tracking in DE require Telemedien-consent separate from
-- the marketing-consent (which lets you SEND the mail). Brevo/Mailchimp
-- bundle both into a single double-opt-in; we keep them separate so
-- transactional opt-out doesn't kill marketing eligibility.
--
-- THREE STATES per recipient:
--   consent_given_at IS NOT NULL  → we may SEND
--   tracking_consent_given_at IS NOT NULL  → we may INJECT pixel + rewrite links
--   neither                       → we cannot send at all
--
-- A recipient can have consent_given_at set but tracking_consent NULL
-- (signed up via legitimate-interest path, no tracking). The send-worker
-- then sends an UN-tracked mail (raw HTML, no pixel, raw links).
--
-- This migration:
--   1. Adds tracking_consent_given_at + tracking_consent_source columns
--   2. Adds a CHECK that consent_revoked_at >= consent_given_at
--   3. Audit-row only (no backfill -- existing rows stay NULL = no tracking)
--
-- After this migration, _send_paranoid._build_mail must pre-check
-- recipient.tracking_consent_given_at before invoking inject_open_pixel
-- / rewrite_links. The per-row column lookup happens in
-- _resolve_recipient_merge_fields (already running) -- we add the field
-- there in a follow-up code change.
--
-- Apply:
--   docker cp 024_tracking_consent.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/024_tracking_consent.sql

BEGIN;

ALTER TABLE marketing.emails
    ADD COLUMN IF NOT EXISTS tracking_consent_given_at  timestamptz,
    ADD COLUMN IF NOT EXISTS tracking_consent_source    text,
    ADD COLUMN IF NOT EXISTS tracking_consent_revoked_at timestamptz;

COMMENT ON COLUMN marketing.emails.tracking_consent_given_at IS
    'Separate from consent_given_at. NULL means the send-worker MUST send '
    'an un-tracked mail (no pixel, no link-rewrite). Set when the recipient '
    'opted into open/click tracking via a tracking-aware consent flow.';

COMMENT ON COLUMN marketing.emails.tracking_consent_source IS
    'Free-text origin (e.g., "double-opt-in:2026-06-08", "manual:operator", '
    '"imported:legacy"). For audit only.';

COMMENT ON COLUMN marketing.emails.tracking_consent_revoked_at IS
    'When the recipient retracted tracking-consent. Once set, NEVER unset '
    '(retrieving consent requires a new tracking_consent_given_at AFTER '
    'tracking_consent_revoked_at, and the latter stays as historical record).';

-- Sanity: revoked >= given (when both present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'emails_tracking_consent_revoked_after_given'
    ) THEN
        ALTER TABLE marketing.emails
            ADD CONSTRAINT emails_tracking_consent_revoked_after_given
            CHECK (
                tracking_consent_revoked_at IS NULL
                OR tracking_consent_given_at IS NULL
                OR tracking_consent_revoked_at >= tracking_consent_given_at
            );
    END IF;
END$$;

-- Partial index for the send-worker's "may I track?" query
CREATE INDEX IF NOT EXISTS idx_emails_tracking_consent_active
    ON marketing.emails (email)
    WHERE tracking_consent_given_at IS NOT NULL
      AND tracking_consent_revoked_at IS NULL;

-- Audit row
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:024',
    'tracking_consent.columns_added',
    'marketing.emails',
    jsonb_build_object(
        'columns', jsonb_build_array(
            'tracking_consent_given_at',
            'tracking_consent_source',
            'tracking_consent_revoked_at'
        ),
        'note',
        'No backfill. Every existing row defaults to NULL = no tracking. '
        '_send_paranoid._build_mail must read this column and skip '
        'tracking injection when NULL (or revoked).'
    )
);

COMMIT;
