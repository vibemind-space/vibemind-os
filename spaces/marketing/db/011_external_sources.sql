-- ============================================================================
-- Marketing-Ops: external integration sources registry
-- ============================================================================
-- Phase-2 expansion of the Hand-bridge: track which external integrations
-- (OpenFang skills, channels, hands) have written into audience_proposals,
-- when they last ran, and what their capability envelope is.
--
-- THIS MIGRATION ADDS ZERO NEW WRITE PATHS TO THE SEND PIPELINE.
--
-- Every integration's `can_send` is set to false AND there is a CHECK
-- constraint enforcing that -- the column exists ONLY so that the
-- enforcement is self-documenting in psql. To make an integration
-- send-capable, you would need a NEW migration that drops the CHECK,
-- explicitly justifies why, and adds the equivalent of the 12-gate
-- stack to that channel. Phase 1 has none of that.
--
-- Capability envelope:
--   * can_read           -- pull data IN from the source (search, files, db)
--   * can_write_proposal -- write a row to marketing.audience_proposals
--                           with the configured source label
--   * can_send           -- HARD FALSE FOR EVERY ROW (CHECK constraint)
--
-- Apply:
--   docker cp 011_external_sources.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/011_external_sources.sql

BEGIN;

-- ─── 1. external_sources registry ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.external_sources (
    -- Stable kebab-case kind identifier (e.g. 'gmail-search', 'notion-page').
    -- Must be in the Python ALLOWED_INTEGRATION_KINDS allowlist.
    kind                 text PRIMARY KEY,
    label                text NOT NULL,
    description          text DEFAULT '',
    -- Category for UI grouping; mirrors the OpenFang skill categories
    -- visible in the screenshot (Data & Analytics, Productivity, etc.).
    category             text NOT NULL,
    can_read             boolean NOT NULL DEFAULT true,
    can_write_proposal   boolean NOT NULL DEFAULT true,
    -- CHECK enforces send-isolation at the schema level. Removing this
    -- check requires a deliberate migration with the equivalent of the
    -- 12-gate send-worker stack -- see _send_paranoid.py.
    can_send             boolean NOT NULL DEFAULT false
                         CHECK (can_send = false),
    -- Hand or skill id this source talks to in OpenFang (when relevant).
    openfang_skill       text,
    -- env vars / API keys this source needs to be operational.
    required_env         jsonb DEFAULT '[]'::jsonb,
    -- Last successful read; null = never run.
    last_synced_at       timestamptz,
    -- Aggregated metrics: how many proposals + lead-candidates this
    -- source produced so far. Updated on each successful import.
    proposals_generated  integer NOT NULL DEFAULT 0
                         CHECK (proposals_generated >= 0),
    candidates_collected integer NOT NULL DEFAULT 0
                         CHECK (candidates_collected >= 0),
    -- Operational gate: an operator can disable a source at runtime
    -- without dropping the row. import-tools refuse to write when
    -- enabled = false. Default true.
    enabled              boolean NOT NULL DEFAULT true,
    created_at           timestamptz DEFAULT now(),
    updated_at           timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_external_sources_enabled
    ON marketing.external_sources(enabled);
CREATE INDEX IF NOT EXISTS idx_external_sources_category
    ON marketing.external_sources(category);

COMMENT ON TABLE marketing.external_sources IS
    'Read-only / proposal-only integrations registry. NEVER on the send '
    'path. can_send=false is enforced by CHECK; removing it requires a '
    'new migration + the 12-gate send-worker contract for that channel.';

GRANT ALL ON marketing.external_sources TO service_role;

-- ─── 2. Touch updated_at on UPDATE ──────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing._external_sources_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_external_sources_updated_at
    ON marketing.external_sources;
CREATE TRIGGER trg_external_sources_updated_at
    BEFORE UPDATE ON marketing.external_sources
    FOR EACH ROW
    EXECUTE FUNCTION marketing._external_sources_updated_at();

-- ─── 3. Seed the Phase-1 allowlist of integrations ──────────────────────
-- These mirror the Python ALLOWED_INTEGRATION_KINDS allowlist. Adding a
-- new kind requires (a) seeding here, (b) adding to the Python frozenset.
-- Both edits = code review = no silent expansion.
INSERT INTO marketing.external_sources
    (kind, label, description, category, openfang_skill, required_env)
VALUES
    ('gmail-search',  'Gmail / Workspace Search',
     'Read Gmail messages via Gog skill (Google Workspace CLI). '
     'Search past correspondence for lead signals (e.g. inbound replies, '
     'event RSVPs) and stage them as audience proposals.',
     'data', 'gog', '["GOOGLE_OAUTH_TOKEN"]'::jsonb),
    ('notion-page',   'Notion Page Import',
     'Import contact lists or campaign notes from Notion pages. Reads '
     'pages/databases via the Notion skill, extracts emails, stages as '
     'proposals.',
     'productivity', 'notion', '["NOTION_API_KEY"]'::jsonb),
    ('sheets-row',    'Google Sheets Row Import',
     'Import a contact list from a Google Sheets range. Each row becomes '
     'a lead-candidate within one audience proposal. Read-only -- never '
     'writes back to the sheet.',
     'data', 'gog', '["GOOGLE_OAUTH_TOKEN"]'::jsonb),
    ('tavily-search', 'Tavily / Web Search',
     'Run a Tavily web-search query, parse results for contact info, '
     'stage as proposal. Useful for ICP discovery without LinkedIn.',
     'research', 'tavily',
     '["TAVILY_API_KEY"]'::jsonb),
    ('manual-csv',    'Manual CSV Import',
     'Operator-provided CSV file with at minimum an email column. The '
     'safest source -- no external API, no LLM, no Hand involved.',
     'data', NULL, '[]'::jsonb)
ON CONFLICT (kind) DO NOTHING;

-- ─── 4. Audit ───────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:011',
    'schema.add_table_seed',
    'marketing.external_sources',
    jsonb_build_object(
        'table_added', 'marketing.external_sources',
        'check_constraint', 'can_send = false',
        'kinds_seeded', jsonb_build_array(
            'gmail-search', 'notion-page', 'sheets-row',
            'tavily-search', 'manual-csv'
        ),
        'send_impact', 'none -- every integration is proposal-only by schema',
        'expansion_rule',
            'adding a new kind requires BOTH a seed row here AND an entry '
            'in ALLOWED_INTEGRATION_KINDS in marketing.tools.integrations'
    )
);

COMMIT;
