-- ============================================================================
-- Marketing-Ops: audience_proposals + lead_candidates staging tables
-- ============================================================================
-- Phase-2-bridge between OpenFang Hands and the marketing pipeline.
--
-- Why staging:
--   Hands (Lead Hand, Researcher Hand, Collector Hand) generate
--   candidate audiences + leads via LLM-driven web research. LLMs
--   hallucinate -- "NEVER fabricate" in the prompt is not a hard
--   guarantee. We therefore land Hand output in DEDICATED staging
--   tables that are NEVER consumed by send_campaign directly. A
--   human (or future review-agent) must explicitly promote a
--   proposal to a real audience via /api/proposals/{id}/approve
--   before any send-pipeline filter even sees it.
--
-- Bidirectional bridge:
--   * B (event-stream): Hand publishes "marketing.audience_proposal"
--     event -> runner consumes -> calls propose_audience tool ->
--     writes here.
--   * A (direct tool): OpenFang registers `marketing_propose_audience`
--     tool -> Hand calls it directly -> HTTP POST /api/proposals ->
--     writes here.
--   * C (reverse): marketing-API's request_hand_research kicks off
--     a Hand task -> Hand eventually writes via A or B back here.
--
-- Tables:
--   audience_proposals -- proposed audience definitions (filter_dsl
--     + descriptive criteria from the Hand)
--   lead_candidates -- per-proposal candidate emails Hand discovered;
--     normalised but NOT trusted: smtp_valid stays -1 (unknown), needs
--     external verification before reaching marketing.emails
--
-- Approval flow (NOT in this migration -- next phase):
--   approve(proposal_id) -> validates lead_candidates emails, inserts
--   the survivors into marketing.emails (with consent_given_at NULL,
--   source='proposal:<id>'), inserts the audience into marketing.audiences,
--   and copies surviving lead_candidates into marketing.audience_members.
--
-- All writes route through tool-layer or HTTP -- never expose service_role
-- DML to Hands directly. Hands talk via the bridge.
--
-- Apply:
--   docker cp 010_audience_proposals.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/010_audience_proposals.sql

BEGIN;

-- ─── 1. audience_proposals ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.audience_proposals (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name              text NOT NULL,
    description       text DEFAULT '',
    -- The Hand-suggested ICP/filter spec (jsonb -- same shape as
    -- marketing.audiences.filter_dsl so a human can copy after approval).
    filter_dsl        jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Why this proposal exists (research summary, growth signals).
    rationale         text DEFAULT '',
    -- Who generated this: 'lead-hand', 'researcher-hand', 'collector-hand',
    -- 'manual', etc.
    source            text NOT NULL DEFAULT 'hand:unknown',
    -- Pending review by default. NEVER auto-promoted by send-worker --
    -- approval is an explicit action (not in this migration).
    status            text NOT NULL DEFAULT 'pending_review'
                      CHECK (status IN ('pending_review','approved','rejected','archived')),
    -- Free-form Hand-generated notes (LLM output).
    hand_notes        text DEFAULT '',
    -- If/when a human approves, link to the real audience that got created.
    approved_audience_id uuid REFERENCES marketing.audiences(id) ON DELETE SET NULL,
    approved_at       timestamptz,
    approved_by       text,
    created_at        timestamptz DEFAULT now(),
    updated_at        timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_proposals_status
    ON marketing.audience_proposals(status)
    WHERE status = 'pending_review';
CREATE INDEX IF NOT EXISTS idx_proposals_source ON marketing.audience_proposals(source);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON marketing.audience_proposals(created_at DESC);

COMMENT ON TABLE marketing.audience_proposals IS
    'Hand-generated audience suggestions awaiting human review. NEVER read by '
    'send-worker -- approval flow promotes survivors into marketing.audiences.';

GRANT ALL ON marketing.audience_proposals TO service_role;

-- ─── 2. lead_candidates ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.lead_candidates (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id       uuid REFERENCES marketing.audience_proposals(id) ON DELETE CASCADE,
    email             text NOT NULL,
    -- Same shape as marketing.emails for easy promotion later.
    display_name      text DEFAULT '',
    company           text DEFAULT '',
    title             text DEFAULT '',
    domain            text DEFAULT '',
    -- NOT verified: stays -1 until external SMTP-validation. We do NOT
    -- trust Hand-claimed validity (LLM may have hallucinated MX).
    smtp_valid        smallint DEFAULT -1
                      CHECK (smtp_valid IN (-1, 0, 1)),
    -- Hand-reported confidence 0.0-1.0 (e.g. "found on LinkedIn" = 0.9,
    -- "guessed via email pattern" = 0.3).
    confidence        real DEFAULT 0.0
                      CHECK (confidence >= 0.0 AND confidence <= 1.0),
    -- Where the Hand says it found this lead (URL / source description).
    discovery_source  text DEFAULT '',
    discovery_query   text DEFAULT '',
    -- Full JSON dump of whatever the Hand collected -- forensic only.
    raw_enrichment    jsonb DEFAULT '{}'::jsonb,
    created_at        timestamptz DEFAULT now()
);
-- Uniqueness within a proposal: a Hand shouldn't list the same email
-- twice in one proposal (deduplication is the Hand's job per its prompt).
CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_candidates_proposal_email
    ON marketing.lead_candidates(proposal_id, email);
CREATE INDEX IF NOT EXISTS idx_lead_candidates_email
    ON marketing.lead_candidates(email);
CREATE INDEX IF NOT EXISTS idx_lead_candidates_domain
    ON marketing.lead_candidates(domain);

COMMENT ON TABLE marketing.lead_candidates IS
    'Hand-discovered email candidates linked to a proposal. smtp_valid=-1 '
    'until external verification; never trusted for send until promoted.';

GRANT ALL ON marketing.lead_candidates TO service_role;

-- ─── 3. updated_at trigger on audience_proposals ────────────────────────
CREATE OR REPLACE FUNCTION marketing._proposals_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_proposals_updated_at ON marketing.audience_proposals;
CREATE TRIGGER trg_proposals_updated_at
    BEFORE UPDATE ON marketing.audience_proposals
    FOR EACH ROW
    EXECUTE FUNCTION marketing._proposals_updated_at();

-- ─── 4. Audit ───────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:010',
    'schema.add_tables',
    'marketing.audience_proposals,marketing.lead_candidates',
    jsonb_build_object(
        'tables_added', jsonb_build_array(
            'marketing.audience_proposals (pending_review by default)',
            'marketing.lead_candidates (smtp_valid=-1 by default)'
        ),
        'purpose',
            'Phase-2 bridge from OpenFang Hands (Lead, Researcher, Collector) -- '
            'Hand output lands here for human review BEFORE entering the send-pipeline. '
            'send-worker never reads these tables.',
        'approval_flow',
            'NOT in this migration. Future POST /api/proposals/{id}/approve will '
            'promote survivors into marketing.emails + marketing.audiences after '
            'external SMTP-validation.'
    )
);

COMMIT;
