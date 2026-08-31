-- ============================================================================
-- Schicht 7.0b hardening — remove approval_token_raw column
-- ============================================================================
-- Migration 031 stored the raw HMAC approval-token alongside the hash so the
-- OpenFang-bridge could re-present it on /approve. Security review (HIGH)
-- flagged this as defeated-hashing: any DB-read leaks usable tokens, and
-- it stores a credential intended for a different auth boundary.
--
-- Replacement: dedicated bridge-routes /api/broadcast_proposals/{id}/approve_via_bridge
-- and /reject_via_bridge authenticate via MARKETING_PROPOSAL_API_KEY +
-- server-side openfang_approval_id match. The curator-pathway keeps the
-- HMAC-token model (hash-only at rest) unchanged.

BEGIN;

ALTER TABLE marketing.broadcast_proposals DROP COLUMN IF EXISTS approval_token_raw;
ALTER TABLE marketing.reply_proposals     DROP COLUMN IF EXISTS approval_token_raw;

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:032',
    'security_hardening.drop_token_raw',
    'marketing.broadcast_proposals',
    jsonb_build_object(
        'columns_removed', jsonb_build_array(
            'broadcast_proposals.approval_token_raw',
            'reply_proposals.approval_token_raw'
        ),
        'reason', 'HIGH-finding from security review: raw HMAC stored at rest defeats the hash. '
                  'Bridge now uses dedicated approve_via_bridge route with worker API-key + '
                  'server-side openfang_approval_id match.'
    )
);

COMMIT;
