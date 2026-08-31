-- Phase 11.U.J — add structured-content + formatting columns to canvas_nodes.
-- The Voice-process CanvasRepository.update_node() expects these columns; with
-- the local SQLite schema they exist, but on Supabase they were missing, so
-- every format_idea_as_* tool call silently failed at the PostgreSQL UPDATE
-- (success-message was wrongly reported in the MCP tool wrapper).
--
-- Adding all four nullable so old rows stay valid.

ALTER TABLE canvas_nodes
    ADD COLUMN IF NOT EXISTS format_schema jsonb DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS content_json jsonb DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS previous_content_json jsonb DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS last_formatted timestamptz DEFAULT NULL;

-- Realtime publication already covers canvas_nodes; no further changes there.
