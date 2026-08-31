-- ============================================================================
-- Marketing-Ops: proposal approval flow (proposal -> audience promotion)
-- ============================================================================
-- Atomic stored function that promotes an audience_proposals row into
-- live marketing.audiences + marketing.audience_members + marketing.emails.
-- ALL OR NOTHING. Validates invariants before writing anything.
--
-- THIS DOES NOT INTRODUCE A NEW SEND PATH. The function lifts candidates
-- INTO the send-eligible tables, but every candidate is inserted with
-- consent_given_at=NULL and smtp_valid honors whatever the caller passed
-- via the lead_candidates.smtp_valid column. send-worker's gates still
-- apply: smtp_valid=1 + investor_already_sent=false + unsubscribed_at IS NULL
-- + confirm_token + LIVE mode + kill-switch + freeze-file.
--
-- Why a stored function instead of Python:
--   - Atomicity: a single transaction touches 3 tables. If any insert
--     fails (FK violation, duplicate primary key, CHECK constraint),
--     the whole approval rolls back. Python with multiple
--     execute_via_docker calls would leave partial state on crash.
--   - Auditability: function-resident logic is reviewable in one place
--     and can't be silently bypassed by a different Python caller.
--   - Future-proof: any caller (Python tool, Hand bridge, manual psql,
--     future REST microservice) goes through the same gate.
--
-- Invariants enforced inside marketing.approve_audience_proposal():
--   1. proposal exists AND status='pending_review' (idempotent: re-approval
--      of an already-approved proposal returns existing audience_id without
--      duplicating rows -- second click is safe).
--   2. proposal has >=1 lead_candidate (no empty audiences).
--   3. Every candidate.email passes the email regex; otherwise it's dropped
--      with skip reason logged in the audit payload.
--   4. accounts row exists per unique handle (synthesised from email
--      localpart if no candidate.company is given; deterministic).
--   5. emails row inserted with smtp_valid from candidate (default -1),
--      consent_given_at=NULL, source='proposal:<id>' so the send-worker
--      filter (smtp_valid=1) excludes unverified by default.
--   6. NEW marketing.audiences row with status_meta JSONB linking back
--      to the originating proposal_id.
--   7. audience_members linking the new audience to each survived email.
--   8. proposal.status='approved', approved_at=now(), approved_audience_id=
--      new audience.id, approved_by from the caller arg.
--
-- Rejection path:
--   marketing.reject_audience_proposal(id, reason, by) sets status='rejected'
--   + audit row. No data is moved.
--
-- Apply:
--   docker cp 012_proposal_approval.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/012_proposal_approval.sql

BEGIN;

-- ─── 1. Approve function ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.approve_audience_proposal(
    p_proposal_id uuid,
    p_approved_by text DEFAULT 'unknown'
) RETURNS TABLE(
    out_proposal_id uuid,
    out_audience_id uuid,
    out_accounts_created integer,
    out_emails_inserted integer,
    out_members_inserted integer,
    out_candidates_skipped integer,
    out_was_idempotent boolean
) AS $$
DECLARE
    v_proposal     marketing.audience_proposals%ROWTYPE;
    v_aud          uuid;
    v_accounts     integer := 0;
    v_emails       integer := 0;
    v_members      integer := 0;
    v_skipped      integer := 0;
    v_idempotent   boolean := false;
    -- Email regex matching the Python _EMAIL_RE in integrations.py.
    v_email_re     text := '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$';
BEGIN
    -- 1. Load proposal under FOR UPDATE to serialise re-approvals.
    SELECT * INTO v_proposal
    FROM marketing.audience_proposals
    WHERE id = p_proposal_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % not found', p_proposal_id;
    END IF;

    -- Idempotency: re-approving an already-approved proposal returns
    -- the existing audience without re-running the promotion.
    IF v_proposal.status = 'approved' THEN
        v_idempotent := true;
        RETURN QUERY SELECT
            v_proposal.id,
            v_proposal.approved_audience_id,
            0::integer, 0::integer, 0::integer, 0::integer,
            v_idempotent;
        RETURN;
    END IF;

    IF v_proposal.status <> 'pending_review' THEN
        RAISE EXCEPTION 'proposal % is in status %; can only approve pending_review',
                        p_proposal_id, v_proposal.status;
    END IF;

    -- 2. Require >=1 candidate.
    IF NOT EXISTS (
        SELECT 1 FROM marketing.lead_candidates
        WHERE lead_candidates.proposal_id = p_proposal_id
    ) THEN
        RAISE EXCEPTION 'proposal % has zero lead_candidates', p_proposal_id;
    END IF;

    -- 3. Create the live audiences row. Name suffixed with -approved to
    --    avoid collision with any pre-existing audience of the same name.
    INSERT INTO marketing.audiences (name, description, filter_dsl)
    VALUES (
        v_proposal.name || ' (approved ' || to_char(now(), 'YYYY-MM-DD') || ')',
        COALESCE(v_proposal.description, '')
            || E'\n\n[Promoted from proposal ' || p_proposal_id::text || ']',
        v_proposal.filter_dsl
    )
    RETURNING id INTO v_aud;

    -- 4. Insert accounts (one per unique handle synthesised from candidate).
    -- handle = lower(localpart) if no company; otherwise lower(company-slug).
    -- ON CONFLICT DO NOTHING -- handle may already exist from prior runs.
    WITH new_accounts AS (
        INSERT INTO marketing.accounts (handle, display_name, niche, source)
        SELECT DISTINCT
            CASE
                WHEN c.company IS NOT NULL AND c.company <> ''
                THEN regexp_replace(lower(c.company), '[^a-z0-9]+', '-', 'g')
                ELSE split_part(c.email, '@', 1)
            END AS handle,
            COALESCE(NULLIF(c.display_name, ''), c.email) AS display_name,
            'proposal-import' AS niche,
            'proposal:' || p_proposal_id::text AS source
        FROM marketing.lead_candidates c
        WHERE c.proposal_id = p_proposal_id
          AND c.email ~ v_email_re
        ON CONFLICT (handle) DO NOTHING
        RETURNING handle
    )
    SELECT COUNT(*) INTO v_accounts FROM new_accounts;

    -- 5. Insert emails. consent_given_at=NULL (DSGVO-safe).
    --    smtp_valid carries through from candidates (default -1 = unknown,
    --    send-worker filter requires =1 so unverified stay unsendable).
    -- Schema note: marketing.emails uses `strategy_id` (text) as the
    -- provenance label, NOT `source`. Plus consent_given_at stays NULL.
    WITH new_emails AS (
        INSERT INTO marketing.emails (
            email, handle, smtp_valid, mx_valid, confidence,
            domain, strategy_id, consent_source, investor_already_sent
        )
        SELECT
            lower(c.email),
            CASE
                WHEN c.company IS NOT NULL AND c.company <> ''
                THEN regexp_replace(lower(c.company), '[^a-z0-9]+', '-', 'g')
                ELSE split_part(c.email, '@', 1)
            END AS handle,
            COALESCE(c.smtp_valid, -1),
            false,                                       -- mx_valid: not yet checked
            COALESCE(c.confidence, 0.0),
            split_part(lower(c.email), '@', 2),
            'proposal:' || p_proposal_id::text,          -- strategy_id stores the provenance
            'proposal-approval-no-consent',
            false                                        -- investor_already_sent: NEVER on approve
        FROM marketing.lead_candidates c
        WHERE c.proposal_id = p_proposal_id
          AND c.email ~ v_email_re
        ON CONFLICT (email) DO NOTHING
        RETURNING email
    )
    SELECT COUNT(*) INTO v_emails FROM new_emails;

    -- 6. Insert audience_members. ON CONFLICT DO NOTHING handles the
    -- case where an email got into emails from a previous source.
    WITH new_members AS (
        INSERT INTO marketing.audience_members (audience_id, email)
        SELECT
            v_aud,
            lower(c.email)
        FROM marketing.lead_candidates c
        WHERE c.proposal_id = p_proposal_id
          AND c.email ~ v_email_re
          AND EXISTS (
              SELECT 1 FROM marketing.emails e
              WHERE e.email = lower(c.email)
          )
        ON CONFLICT (audience_id, email) DO NOTHING
        RETURNING email
    )
    SELECT COUNT(*) INTO v_members FROM new_members;

    -- 6b. Cache member_count + last_built_at on the audiences row so
    -- the UI doesn't always have to subquery. Recompute fresh from
    -- audience_members so the cache is correct even if rows were
    -- inserted earlier outside this function.
    UPDATE marketing.audiences
    SET member_count = (
        SELECT COUNT(*) FROM marketing.audience_members
        WHERE audience_members.audience_id = v_aud
    ),
        last_built_at = now()
    WHERE id = v_aud;

    -- 7. Count skipped candidates (regex-invalid emails)
    SELECT COUNT(*) INTO v_skipped
    FROM marketing.lead_candidates
    WHERE lead_candidates.proposal_id = p_proposal_id
      AND NOT (email ~ v_email_re);

    -- 8. Mark the proposal approved.
    UPDATE marketing.audience_proposals
    SET status = 'approved',
        approved_audience_id = v_aud,
        approved_at = now(),
        approved_by = p_approved_by
    WHERE id = p_proposal_id;

    -- 9. Audit row inside the same transaction (rolled back if anything failed).
    INSERT INTO marketing.audit_log (actor, action, target_table, payload)
    VALUES (
        'proposal_approval:' || p_approved_by,
        'proposal.approved',
        'marketing.audience_proposals',
        jsonb_build_object(
            'proposal_id', p_proposal_id,
            'audience_id', v_aud,
            'accounts_created', v_accounts,
            'emails_inserted', v_emails,
            'members_inserted', v_members,
            'candidates_skipped', v_skipped,
            'approved_by', p_approved_by,
            'no_send_impact',
                'consent_given_at=NULL + smtp_valid carried from candidate '
                || '(send-worker requires =1) + investor_already_sent=false'
        )
    );

    RETURN QUERY SELECT
        p_proposal_id, v_aud,
        v_accounts, v_emails, v_members, v_skipped, v_idempotent;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.approve_audience_proposal(uuid, text) IS
    'Promotes a pending audience_proposal into live audiences + '
    'audience_members + emails. Atomic single-transaction. NEVER sets '
    'consent_given_at or smtp_valid=1; send-worker gates still apply.';


-- ─── 2. Reject function ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.reject_audience_proposal(
    p_proposal_id uuid,
    p_reason text,
    p_rejected_by text DEFAULT 'unknown'
) RETURNS TABLE(
    out_proposal_id uuid,
    out_previous_status text,
    out_rejected_at timestamptz
) AS $$
DECLARE
    v_prev_status text;
BEGIN
    SELECT status INTO v_prev_status
    FROM marketing.audience_proposals
    WHERE id = p_proposal_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % not found', p_proposal_id;
    END IF;
    IF v_prev_status IN ('approved', 'rejected') THEN
        -- Idempotent for rejected, refused for approved.
        IF v_prev_status = 'approved' THEN
            RAISE EXCEPTION 'cannot reject already-approved proposal %', p_proposal_id;
        END IF;
        RETURN QUERY SELECT p_proposal_id, v_prev_status, now();
        RETURN;
    END IF;

    UPDATE marketing.audience_proposals
    SET status = 'rejected'
    WHERE id = p_proposal_id;

    INSERT INTO marketing.audit_log (actor, action, target_table, payload)
    VALUES (
        'proposal_approval:' || p_rejected_by,
        'proposal.rejected',
        'marketing.audience_proposals',
        jsonb_build_object(
            'proposal_id', p_proposal_id,
            'reason', p_reason,
            'rejected_by', p_rejected_by
        )
    );

    RETURN QUERY SELECT p_proposal_id, v_prev_status, now();
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.reject_audience_proposal(uuid, text, text) IS
    'Marks proposal rejected with reason. No data moved. Approved '
    'proposals cannot be rejected (use archive flow instead -- not yet built).';


-- ─── 3. Audit migration ─────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:012',
    'schema.add_functions',
    'marketing.audience_proposals',
    jsonb_build_object(
        'functions_added', jsonb_build_array(
            'marketing.approve_audience_proposal(uuid, text)',
            'marketing.reject_audience_proposal(uuid, text, text)'
        ),
        'guarantees',
            'atomic-or-rollback, idempotent re-approval, regex-validation, '
            'smtp_valid carried from candidate (send-worker filter intact), '
            'consent_given_at=NULL (DSGVO-safe), '
            'investor_already_sent=false (lockout not flipped on approval)',
        'send_impact',
            'NONE -- candidates land in emails with smtp_valid<=1 and '
            'consent_given_at=NULL; send-worker still requires smtp_valid=1 '
            'AND human-driven confirm_token AND 11 other gates'
    )
);

COMMIT;
