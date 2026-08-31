-- Migration: SWE Design Wizard Sessions
-- Date: 2026-08-06
--
-- The RE wizard (spaces/shuttles/swe_desgine, dashboard :8080) runs its
-- mine -> validate -> decide -> improve loop BEFORE (or without) a pipeline
-- run, so its results had nowhere to persist: swe_design_runs is keyed on
-- completed pipeline runs and swe_design_artifacts hangs off that FK.
--
-- Decision (user, 2026-08-06): dedicated table instead of pseudo-runs, so
-- run statistics stay clean and wizard-only sessions survive. One row per
-- wizard session; the full validation report and the final requirements
-- live as JSONB on the row (a report is one coherent document - no
-- artifact-table indirection needed). run_id is back-filled when a session
-- later becomes an actual pipeline run -> traceability in both directions.

CREATE TABLE IF NOT EXISTS swe_design_wizard_sessions (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,

    -- Upsert key: the wizard UI threads a correlation_id through
    -- validate-batch and improve; both phases land on the same row.
    -- (Postgres UNIQUE allows multiple NULLs - sessions without a
    -- correlation_id simply insert fresh rows.)
    correlation_id TEXT UNIQUE,

    status TEXT DEFAULT 'validated',          -- validated, completed, failed
    source_files JSONB DEFAULT '[]',          -- which documents were mined

    -- Validation parameters
    model TEXT,
    threshold FLOAT,

    -- Counts / quality metrics
    mined_count INTEGER DEFAULT 0,
    validated_count INTEGER DEFAULT 0,
    rewritten_count INTEGER DEFAULT 0,
    initial_pass_rate FLOAT,
    final_pass_rate FLOAT,

    -- Payloads
    validation_report JSONB DEFAULT '[]',     -- per-requirement scores, verdicts, mock flags
    requirements JSONB DEFAULT '[]',          -- requirement set (post-improve = final)

    -- Back-link, filled when the session's requirements start a pipeline run
    run_id TEXT REFERENCES swe_design_runs(id) ON DELETE SET NULL,

    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_wizard_sessions_status
    ON swe_design_wizard_sessions(status);
CREATE INDEX IF NOT EXISTS idx_wizard_sessions_run
    ON swe_design_wizard_sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_wizard_sessions_started
    ON swe_design_wizard_sessions(started_at DESC);

-- ═══════════════════════════════════════════════════════════
-- RLS - allow-all, matching every other swe_design table
-- ═══════════════════════════════════════════════════════════
ALTER TABLE swe_design_wizard_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "allow_all_swe_design_wizard_sessions" ON swe_design_wizard_sessions;
CREATE POLICY "allow_all_swe_design_wizard_sessions" ON swe_design_wizard_sessions
    FOR ALL USING (true) WITH CHECK (true);

-- Grants for the PostgREST roles (20260521 needed these applied manually
-- afterwards - bake them in this time)
GRANT ALL ON TABLE swe_design_wizard_sessions TO anon, authenticated, service_role;

-- ═══════════════════════════════════════════════════════════
-- Realtime - dashboard can subscribe to session progress
-- ═══════════════════════════════════════════════════════════
ALTER PUBLICATION supabase_realtime ADD TABLE swe_design_wizard_sessions;
