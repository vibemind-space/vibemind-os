-- Migration: SWE Design (Requirements Engineer) pipeline persistence
-- Date: 2026-05-21
--
-- Until now the RE pipeline (vibemind-os/spaces/shuttles/swe_desgine/) wrote
-- its output only to the filesystem (enterprise_output/{name}_{ts}/). This
-- migration makes Supabase the source of truth for *structure* (runs +
-- artifacts), while the filesystem stays as pipeline scratch (checkpoints /
-- resume). A future Gitea sync will own versioned artifact *content* — the
-- `gitea_commit_sha` column is the placeholder for that handoff.
--
-- Two tables:
--   swe_design_runs      — one row per completed RE pipeline run (manifest)
--   swe_design_artifacts — one row per generated artifact (user stories,
--                          mermaid diagram, data dictionary, .feature, ...)

-- ═══════════════════════════════════════════════════════════
-- swe_design_runs — pipeline run manifest
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS swe_design_runs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    pipeline_id TEXT,                         -- PipelineManifest.pipeline_id
    project_name TEXT NOT NULL,
    slug TEXT NOT NULL,                       -- _slugify(project_name)
    status TEXT DEFAULT 'in_progress',        -- in_progress, completed, failed
    domain TEXT DEFAULT 'custom',

    -- Stage progress
    total_stages INTEGER DEFAULT 0,
    completed_stages INTEGER DEFAULT 0,

    -- Cost / telemetry
    total_cost_usd FLOAT DEFAULT 0.0,
    total_tokens INTEGER DEFAULT 0,
    total_llm_calls INTEGER DEFAULT 0,

    -- Links
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    shuttle_id TEXT REFERENCES shuttles(id) ON DELETE SET NULL,

    -- Filesystem scratch location (pipeline checkpoints / resume)
    output_dir TEXT,

    -- Gitea handoff (NULL until the Gitea artifact sync ships)
    gitea_repo TEXT,
    gitea_commit_sha TEXT,

    manifest JSONB DEFAULT '{}',              -- full PipelineManifest.to_dict()
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_swe_design_runs_slug ON swe_design_runs(slug);
CREATE INDEX IF NOT EXISTS idx_swe_design_runs_status ON swe_design_runs(status);
CREATE INDEX IF NOT EXISTS idx_swe_design_runs_project ON swe_design_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_swe_design_runs_created ON swe_design_runs(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- swe_design_artifacts — one row per generated artifact file
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS swe_design_artifacts (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT NOT NULL REFERENCES swe_design_runs(id) ON DELETE CASCADE,

    -- artifact_type examples: user_stories, epics, traceability, data_dictionary,
    --   work_breakdown, api_documentation, mermaid, state_machines, infrastructure,
    --   ui_compositions, test_factories, architecture, gherkin, master_document,
    --   journal, manifest
    artifact_type TEXT NOT NULL,
    name TEXT NOT NULL,                       -- file name, e.g. "user_stories.md"
    rel_path TEXT,                            -- path relative to output_dir

    -- Content: prefer content_json for structured (parsed) artifacts,
    -- content_text for raw markdown / mermaid / .feature source.
    format TEXT DEFAULT 'text',               -- text, markdown, mermaid, json, gherkin
    content_text TEXT,
    content_json JSONB,

    item_count INTEGER DEFAULT 0,             -- e.g. # user stories, # diagrams
    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(run_id, rel_path)
);

CREATE INDEX IF NOT EXISTS idx_swe_design_artifacts_run ON swe_design_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_swe_design_artifacts_type ON swe_design_artifacts(artifact_type);

-- ═══════════════════════════════════════════════════════════
-- RLS — allow-all for local dev (anon key), matching every other table
-- ═══════════════════════════════════════════════════════════
ALTER TABLE swe_design_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE swe_design_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "allow_all_swe_design_runs" ON swe_design_runs;
CREATE POLICY "allow_all_swe_design_runs" ON swe_design_runs
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "allow_all_swe_design_artifacts" ON swe_design_artifacts;
CREATE POLICY "allow_all_swe_design_artifacts" ON swe_design_artifacts
    FOR ALL USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════
-- Realtime — Electron / dashboard can subscribe to run progress
-- ═══════════════════════════════════════════════════════════
ALTER PUBLICATION supabase_realtime ADD TABLE swe_design_runs;
ALTER PUBLICATION supabase_realtime ADD TABLE swe_design_artifacts;
