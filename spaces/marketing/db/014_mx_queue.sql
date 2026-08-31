-- ============================================================================
-- Marketing-Ops: async MX validation queue
-- ============================================================================
-- Why: validate_proposal_mx is synchronous and blocks the HTTP request
-- for the duration of DNS lookups. Large proposals (>50 unique domains)
-- can exceed FastAPI's default request timeout. This migration adds a
-- small queue + worker pattern: HTTP enqueues, a background worker
-- drains. Same final effect on lead_candidates.smtp_valid; same
-- defense-in-depth recheck before approval.
--
-- NO new send path. Same gate-stack applies after approval.
--
-- Apply:
--   docker cp 014_mx_queue.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/014_mx_queue.sql

BEGIN;

-- ─── Job table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.mx_validation_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Either: scope to a single proposal_id, OR scope to a single domain
    -- (one of the two MUST be set; both is fine -- validates this proposal
    -- only for that domain).
    proposal_id     uuid REFERENCES marketing.audience_proposals(id) ON DELETE CASCADE,
    domain          text,
    -- Job state machine. Status text rather than enum for migration flexibility.
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','error','cancelled')),
    -- Set by worker on completion.
    result          jsonb,
    error_message   text,
    -- Bookkeeping
    attempt_count   integer NOT NULL DEFAULT 0,
    -- A worker stamps this when it picks the job up; defense against
    -- another worker grabbing the same job (we use SELECT FOR UPDATE
    -- SKIP LOCKED in the Python claim query).
    started_at      timestamptz,
    finished_at     timestamptz,
    created_at      timestamptz DEFAULT now(),
    -- Audit
    requested_by    text DEFAULT 'http',
    CONSTRAINT mx_jobs_one_target_at_minimum CHECK (
        proposal_id IS NOT NULL OR domain IS NOT NULL
    )
);
CREATE INDEX IF NOT EXISTS idx_mx_jobs_pending
    ON marketing.mx_validation_jobs(created_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_mx_jobs_proposal
    ON marketing.mx_validation_jobs(proposal_id)
    WHERE proposal_id IS NOT NULL;

COMMENT ON TABLE marketing.mx_validation_jobs IS
    'Async MX validation queue. Worker D-like drainer flips smtp_valid '
    'on lead_candidates and stores summary in result.';

GRANT ALL ON marketing.mx_validation_jobs TO service_role;


-- ─── Audit ────────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:014',
    'schema.add_table',
    'marketing.mx_validation_jobs',
    jsonb_build_object(
        'purpose',
            'async queue for big-audience MX validation (>50 unique domains). '
            'HTTP enqueues; worker drains. Same lead_candidates.smtp_valid '
            'updates as the synchronous validate_proposal_mx.',
        'send_impact', 'none -- queue + result are read-only metadata'
    )
);

COMMIT;
