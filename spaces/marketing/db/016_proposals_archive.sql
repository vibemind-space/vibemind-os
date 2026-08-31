-- ============================================================================
-- Marketing-Ops: audience_proposals archive table + archive_old_proposals()
-- ============================================================================
-- Long-term retention story for proposals + lead_candidates:
--
--   active table:  marketing.audience_proposals (pending_review / approved / rejected)
--   archive:       marketing.audience_proposals_archive (history-only, append-only)
--   stored fn:     marketing.archive_old_proposals(days_old, dry_run)
--
-- Why an archive table instead of just status='archived':
--   - The active table is queried by the dashboard + Mockup live binding.
--     A multi-thousand-row table of years-old archived proposals would
--     slow every read.
--   - lead_candidates rows have a FK to audience_proposals(id) with
--     ON DELETE CASCADE -- so moving the parent to archive lets us
--     drop the candidate rows entirely (they're not needed once the
--     proposal is in cold storage; the proposal row keeps a JSONB
--     snapshot of candidate count + sample emails for forensic dig-ins).
--
-- Archive criteria (defaults):
--   - status IN ('approved', 'rejected')
--   - approved_at OR (created_at if rejected) older than `p_days_old` days
--   - Approved proposals that promoted to a live audience are archived
--     too; the audience itself stays untouched (only the proposal-side
--     metadata moves).
--
-- NO send impact. NEVER modifies emails / audiences / audience_members
-- / campaign_sends. Only the staging records move.
--
-- Apply:
--   docker cp 016_proposals_archive.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/016_proposals_archive.sql

BEGIN;

-- ─── 1. Archive table ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.audience_proposals_archive (
    -- Same id as the original row -- restore is a straightforward UPDATE
    -- back.
    id                   uuid PRIMARY KEY,
    name                 text,
    description          text,
    filter_dsl           jsonb,
    rationale            text,
    source               text,
    status               text,
    hand_notes           text,
    approved_audience_id uuid,
    approved_at          timestamptz,
    approved_by          text,
    created_at           timestamptz,
    updated_at           timestamptz,
    -- Bookkeeping
    archived_at          timestamptz NOT NULL DEFAULT now(),
    archived_by          text NOT NULL DEFAULT 'system',
    -- Snapshot of candidates that were attached to this proposal at
    -- archival time. Compact JSONB, NOT a clone of lead_candidates rows
    -- -- so the archive stays light.
    candidate_count      integer NOT NULL DEFAULT 0,
    candidate_sample     jsonb DEFAULT '[]'::jsonb,
    candidate_domains    jsonb DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_proposals_archive_created
    ON marketing.audience_proposals_archive(created_at);
CREATE INDEX IF NOT EXISTS idx_proposals_archive_status
    ON marketing.audience_proposals_archive(status);
CREATE INDEX IF NOT EXISTS idx_proposals_archive_archived
    ON marketing.audience_proposals_archive(archived_at);

COMMENT ON TABLE marketing.audience_proposals_archive IS
    'Cold storage for finalised proposals. Append-only at the operational '
    'layer; restore is via UPDATE audience_proposals back from this row. '
    'lead_candidates are NOT cloned here -- only a compact JSON sample.';

GRANT ALL ON marketing.audience_proposals_archive TO service_role;


-- ─── 2. Stored function: archive_old_proposals ─────────────────────────
-- Moves matching rows into the archive + drops their lead_candidates
-- via the existing ON DELETE CASCADE. Atomic.
CREATE OR REPLACE FUNCTION marketing.archive_old_proposals(
    p_days_old integer DEFAULT 90,
    p_dry_run  boolean DEFAULT false,
    p_archived_by text DEFAULT 'system'
) RETURNS TABLE(
    out_archived_count integer,
    out_dropped_candidates integer,
    out_dry_run boolean
) AS $$
DECLARE
    v_archived integer := 0;
    v_dropped  integer := 0;
    v_cutoff   timestamptz := now() - make_interval(days => p_days_old);
BEGIN
    -- Count candidates we're about to drop (for the response payload).
    SELECT COUNT(*) INTO v_dropped
    FROM marketing.lead_candidates lc
    JOIN marketing.audience_proposals p ON p.id = lc.proposal_id
    WHERE p.status IN ('approved', 'rejected')
      AND COALESCE(p.approved_at, p.updated_at, p.created_at) < v_cutoff;

    -- Dry-run early-exit before any write.
    IF p_dry_run THEN
        SELECT COUNT(*) INTO v_archived
        FROM marketing.audience_proposals p
        WHERE p.status IN ('approved', 'rejected')
          AND COALESCE(p.approved_at, p.updated_at, p.created_at) < v_cutoff;
        RETURN QUERY SELECT v_archived, v_dropped, true;
        RETURN;
    END IF;

    -- Real run: copy to archive (with candidate sample) then DELETE.
    -- The DELETE cascades through lead_candidates.
    WITH targets AS (
        SELECT p.* FROM marketing.audience_proposals p
        WHERE p.status IN ('approved', 'rejected')
          AND COALESCE(p.approved_at, p.updated_at, p.created_at) < v_cutoff
        FOR UPDATE
    ),
    samples AS (
        SELECT
            t.id,
            COUNT(lc.email)                                 AS cand_count,
            -- First 10 emails as the sample
            jsonb_agg(lc.email ORDER BY lc.email)
                FILTER (WHERE lc.email IS NOT NULL)         AS all_emails,
            -- Unique domains
            jsonb_agg(DISTINCT split_part(lc.email,'@',2))
                FILTER (WHERE lc.email IS NOT NULL)         AS domains
        FROM targets t
        LEFT JOIN marketing.lead_candidates lc ON lc.proposal_id = t.id
        GROUP BY t.id
    ),
    inserted AS (
        INSERT INTO marketing.audience_proposals_archive (
            id, name, description, filter_dsl, rationale, source, status,
            hand_notes, approved_audience_id, approved_at, approved_by,
            created_at, updated_at, archived_by,
            candidate_count, candidate_sample, candidate_domains
        )
        SELECT
            t.id, t.name, t.description, t.filter_dsl, t.rationale,
            t.source, t.status, t.hand_notes, t.approved_audience_id,
            t.approved_at, t.approved_by, t.created_at, t.updated_at,
            p_archived_by,
            COALESCE(s.cand_count, 0)::integer,
            -- candidate_sample: first 10 emails
            COALESCE(
                (SELECT jsonb_agg(e)
                 FROM (SELECT jsonb_array_elements_text(s.all_emails) AS e
                       LIMIT 10) sub),
                '[]'::jsonb
            ),
            COALESCE(s.domains, '[]'::jsonb)
        FROM targets t
        LEFT JOIN samples s ON s.id = t.id
        ON CONFLICT (id) DO NOTHING
        RETURNING id
    )
    SELECT COUNT(*) INTO v_archived FROM inserted;

    -- Now delete from the active table. CASCADE drops the lead_candidates.
    DELETE FROM marketing.audience_proposals
    WHERE id IN (
        SELECT id FROM marketing.audience_proposals_archive
        WHERE archived_at > now() - interval '1 minute'
          AND archived_by = p_archived_by
    );

    -- Audit
    INSERT INTO marketing.audit_log (actor, action, target_table, payload)
    VALUES (
        'archival:' || p_archived_by,
        'proposals.archived',
        'marketing.audience_proposals',
        jsonb_build_object(
            'archived_count',     v_archived,
            'dropped_candidates', v_dropped,
            'cutoff_days',        p_days_old,
            'cutoff_timestamp',   v_cutoff
        )
    );

    RETURN QUERY SELECT v_archived, v_dropped, false;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.archive_old_proposals(integer, boolean, text) IS
    'Moves approved/rejected proposals older than p_days_old into '
    'audience_proposals_archive. CASCADE drops lead_candidates; '
    'sample + domains preserved in archive row JSONB. Idempotent.';


-- ─── 3. Restore function (uncommon path; explicit operator action) ─────
CREATE OR REPLACE FUNCTION marketing.restore_proposal_from_archive(
    p_proposal_id uuid,
    p_restored_by text DEFAULT 'unknown'
) RETURNS TABLE(out_proposal_id uuid, out_restored boolean) AS $$
DECLARE
    v_arch marketing.audience_proposals_archive%ROWTYPE;
BEGIN
    SELECT * INTO v_arch
    FROM marketing.audience_proposals_archive
    WHERE id = p_proposal_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no archive row for proposal_id %', p_proposal_id;
    END IF;

    -- INSERT back. lead_candidates are NOT restored -- they were dropped
    -- during archival; only the parent row comes back.
    INSERT INTO marketing.audience_proposals (
        id, name, description, filter_dsl, rationale, source, status,
        hand_notes, approved_audience_id, approved_at, approved_by,
        created_at, updated_at
    )
    VALUES (
        v_arch.id, v_arch.name, v_arch.description, v_arch.filter_dsl,
        v_arch.rationale, v_arch.source, v_arch.status, v_arch.hand_notes,
        v_arch.approved_audience_id, v_arch.approved_at, v_arch.approved_by,
        v_arch.created_at, now()
    )
    ON CONFLICT (id) DO NOTHING;

    -- Remove the archive row + audit
    DELETE FROM marketing.audience_proposals_archive WHERE id = p_proposal_id;

    INSERT INTO marketing.audit_log (actor, action, target_table, payload)
    VALUES (
        'archival:' || p_restored_by,
        'proposal.restored',
        'marketing.audience_proposals',
        jsonb_build_object(
            'proposal_id', p_proposal_id,
            'restored_by', p_restored_by,
            'note', 'lead_candidates NOT restored (dropped on archival)'
        )
    );

    RETURN QUERY SELECT p_proposal_id, true;
END;
$$ LANGUAGE plpgsql;


-- ─── 4. Audit migration ────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:016',
    'schema.add_table_and_functions',
    'marketing.audience_proposals_archive',
    jsonb_build_object(
        'tables_added',    jsonb_build_array('marketing.audience_proposals_archive'),
        'functions_added', jsonb_build_array(
            'marketing.archive_old_proposals(days_old, dry_run, archived_by)',
            'marketing.restore_proposal_from_archive(id, restored_by)'
        ),
        'send_impact', 'none -- only staging records move; emails/audiences untouched'
    )
);

COMMIT;
