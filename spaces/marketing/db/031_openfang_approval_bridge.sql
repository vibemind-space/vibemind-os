-- ============================================================================
-- Schicht 7.0b — Bridge marketing broadcast/reply approvals to OpenFang UI
-- ============================================================================
-- The OpenFang UI at http://127.0.0.1:4200 has an "Execution Approvals" tab
-- (left sidebar -> Agents -> Approvals). It shows pending approval-requests
-- created via POST /api/approvals.
--
-- This migration adds a correlation column so marketing.broadcast_proposals
-- and marketing.reply_proposals can be linked to their OpenFang-approval
-- counterpart. When the curator requests approval, marketing-API will
-- ALSO POST to OpenFang's /api/approvals, then store the returned id here.
--
-- Bridge-poller (Python worker) watches OpenFang for state-changes:
--   pending -> approved   ->   marketing /api/.../approve   (with token)
--   pending -> rejected   ->   marketing /api/.../reject    (with token)
--   pending -> timeout    ->   marketing /api/.../reject    (timeout reason)
--
-- The HMAC-signed marketing approval_token is held by the bridge-poller
-- (not by OpenFang) — preserving the existing single-use security model.
--
-- Apply:
--   docker cp 031_openfang_approval_bridge.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/031_openfang_approval_bridge.sql

BEGIN;

ALTER TABLE marketing.broadcast_proposals
    ADD COLUMN IF NOT EXISTS openfang_approval_id uuid;

ALTER TABLE marketing.reply_proposals
    ADD COLUMN IF NOT EXISTS openfang_approval_id uuid;

COMMENT ON COLUMN marketing.broadcast_proposals.openfang_approval_id IS
    'Correlation to OpenFang execution-approval (POST /api/approvals returns this id). '
    'NULL while status=draft. Set on request_approval, cleared on approve/reject.';

COMMENT ON COLUMN marketing.reply_proposals.openfang_approval_id IS
    'Same as broadcast_proposals.openfang_approval_id — bridges marketing approval to OpenFang UI.';

-- Pending-approvals lookup index (bridge-poller scans every N seconds)
CREATE INDEX IF NOT EXISTS idx_broadcast_proposals_openfang_pending
    ON marketing.broadcast_proposals (openfang_approval_id)
    WHERE status = 'pending_approval' AND openfang_approval_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reply_proposals_openfang_pending
    ON marketing.reply_proposals (openfang_approval_id)
    WHERE status = 'pending_approval' AND openfang_approval_id IS NOT NULL;

-- Bridge-secret-storage: HMAC tokens are minted on request_approval and
-- normally returned ONCE to the curator. With the OpenFang-bridge, we
-- need to keep the token long enough for the poller to relay it back on
-- approve/reject. Store the RAW token (NOT hash) on the proposal row,
-- protected by status='pending_approval' invariant (cleared on resolve).
-- This is a deliberate trade: token-leak via DB-row vs. token-keeping
-- in a separate ephemeral store. We pick the former because:
--   1. The DB is already the source-of-truth + auth-gated.
--   2. The token's purpose is single-use authentication of an
--      approval-callback; an attacker that already has DB-read can
--      tamper with rows directly.
--   3. The token-hash already protects against external token-forgery.
-- The token is cleared (NULL'd) by the approve/reject handlers as
-- before — same single-use semantics.
--
-- SECURITY NOTE (defense-in-depth, added 2026-06-17 after automated review):
-- The mitigations above were code-verified: approval_token_raw is set only on
-- request_approval (server.py:2469), NULL'd on BOTH approve and reject
-- (server.py:2530/2573), and never returned by any GET endpoint. The residual
-- risk the review flags is at-rest exposure: anything that reads the DB FILES
-- (backups, replicas, snapshots) outside the API auth-gate would see live raw
-- tokens for currently-pending rows. The in-app threat model holds (a logical
-- DB-read attacker can tamper directly anyway), but if backups/replicas ever
-- leave the trust boundary, consider encrypting this column at rest with
-- pgcrypto pgp_sym_encrypt() under a KMS-managed key not stored in the DB, and
-- decrypt only inside the bridge-poller. Owner decision — not changed here to
-- avoid breaking the live approval bridge.
--
-- BETTER LONG-TERM FIX (from a second review pass): avoid persisting the
-- user-bound token entirely. The bridge is a trusted server-side actor, so the
-- /approve + /reject endpoints could accept (MARKETING_PROPOSAL_API_KEY +
-- openfang_approval_id) from actor='openfang-bridge' and resolve the proposal
-- server-side — no replayable user token in the DB at all. Alternatively mint a
-- SEPARATE bridge-only token (different audience) so a DB-read never yields the
-- curator-callable token. Either removes approval_token_raw cleanly. Tracked as
-- a hardening item for the marketing owner; not applied here.

ALTER TABLE marketing.broadcast_proposals
    ADD COLUMN IF NOT EXISTS approval_token_raw text;

ALTER TABLE marketing.reply_proposals
    ADD COLUMN IF NOT EXISTS approval_token_raw text;

COMMENT ON COLUMN marketing.broadcast_proposals.approval_token_raw IS
    'Raw HMAC approval-token. Stored only while status=pending_approval so the '
    'OpenFang-bridge-poller can use it on approve-callback. Cleared by approve/reject '
    'handlers same as approval_token_hash. NEVER returned by any GET endpoint.';

COMMENT ON COLUMN marketing.reply_proposals.approval_token_raw IS
    'Raw HMAC approval-token. Same lifecycle + sensitivity as broadcast version.';

INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:031',
    'openfang_approval_bridge.columns_added',
    'marketing.broadcast_proposals',
    jsonb_build_object(
        'columns', jsonb_build_array(
            'broadcast_proposals.openfang_approval_id',
            'broadcast_proposals.approval_token_raw',
            'reply_proposals.openfang_approval_id',
            'reply_proposals.approval_token_raw'
        ),
        'note',
        'Schicht 7.0b: pending approvals visible in OpenFang Approvals UI. '
        'request_approval ALSO creates OpenFang approval-request; bridge-poller '
        'relays approve/reject decisions back to marketing-API with the token. '
        'Token stored raw (not just hash) on pending rows because the bridge needs to '
        're-present it on the callback — same single-use semantics as before.'
    )
);

COMMIT;
