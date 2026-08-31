-- VibeMind Database Schema for Supabase (Postgres)
-- Complete migration from SQLite schema v22 (22 tables)
-- Generated: 2026-04-11

-- ═══════════════════════════════════════════════════════════
-- 1. Ideas / Bubbles
-- ═══════════════════════════════════════════════════════════
-- Enable pgvector for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ideas (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    source TEXT DEFAULT 'voice',
    created_at TIMESTAMPTZ DEFAULT now(),
    score FLOAT DEFAULT 0.0,
    status TEXT DEFAULT 'raw',
    promoted_to_project_id TEXT,
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    agent_id TEXT,
    parent_id TEXT REFERENCES ideas(id) ON DELETE SET NULL,
    embedding_vector vector(384),
    embedding_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);
CREATE INDEX IF NOT EXISTS idx_ideas_score ON ideas(score DESC);
CREATE INDEX IF NOT EXISTS idx_ideas_created ON ideas(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ideas_parent ON ideas(parent_id);

-- ═══════════════════════════════════════════════════════════
-- 2. Projects (promoted ideas + code generation)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    from_idea_id TEXT REFERENCES ideas(id) ON DELETE SET NULL,
    progress FLOAT DEFAULT 0.0,
    metadata JSONB DEFAULT '{}',
    project_path TEXT,
    generation_status TEXT DEFAULT 'pending',
    vnc_port INTEGER,
    job_id TEXT,
    requirements_json TEXT,
    convergence_progress FLOAT DEFAULT 0.0,
    preview_url TEXT,
    tech_stack TEXT,
    error_message TEXT
);

ALTER TABLE ideas ADD CONSTRAINT fk_ideas_project
    FOREIGN KEY (promoted_to_project_id) REFERENCES projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_job_id ON projects(job_id);
CREATE INDEX IF NOT EXISTS idx_projects_generation ON projects(generation_status);

-- ═══════════════════════════════════════════════════════════
-- 3. Canvas Nodes (visual board)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS canvas_nodes (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    node_type TEXT NOT NULL DEFAULT 'note',
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    x FLOAT DEFAULT 0.0,
    y FLOAT DEFAULT 0.0,
    linked_idea_id TEXT REFERENCES ideas(id) ON DELETE SET NULL,
    linked_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    summary TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_canvas_nodes_type ON canvas_nodes(node_type);

-- ═══════════════════════════════════════════════════════════
-- 4. Canvas Edges (connections)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS canvas_edges (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    from_node_id TEXT NOT NULL REFERENCES canvas_nodes(id) ON DELETE CASCADE,
    to_node_id TEXT NOT NULL REFERENCES canvas_nodes(id) ON DELETE CASCADE,
    edge_type TEXT DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_canvas_edges_from ON canvas_edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_canvas_edges_to ON canvas_edges(to_node_id);

-- ═══════════════════════════════════════════════════════════
-- 5. Conversation Sessions
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    summary TEXT,
    agent_id TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conv_sessions_started ON conversation_sessions(started_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 6. Conversation History
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS conversation_history (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conv_history_session ON conversation_history(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_history_ts ON conversation_history(timestamp DESC);

-- ═══════════════════════════════════════════════════════════
-- 7. Shuttles (requirement evaluation pipeline)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS shuttles (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    shuttle_id TEXT NOT NULL UNIQUE,
    bubble_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    bubble_name TEXT NOT NULL,
    score FLOAT DEFAULT 0.0,
    passed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'launching',
    current_stage TEXT DEFAULT 'mining',
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    stage_type TEXT DEFAULT 'full',
    stage_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    requirement_results JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_shuttles_bubble ON shuttles(bubble_id);
CREATE INDEX IF NOT EXISTS idx_shuttles_status ON shuttles(status);
CREATE INDEX IF NOT EXISTS idx_shuttles_created ON shuttles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shuttles_project ON shuttles(project_id);

-- ═══════════════════════════════════════════════════════════
-- 8. Exploration Sessions (AI-Scientist)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS exploration_sessions (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    root_bubble_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    root_bubble_title TEXT,
    exploration_query TEXT,
    status TEXT DEFAULT 'running',
    current_stage INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    total_nodes_explored INTEGER DEFAULT 0,
    best_score FLOAT DEFAULT 0.0,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_exploration_status ON exploration_sessions(status);
CREATE INDEX IF NOT EXISTS idx_exploration_root ON exploration_sessions(root_bubble_id);

-- ═══════════════════════════════════════════════════════════
-- 9. Exploration Nodes
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS exploration_nodes (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES exploration_sessions(id) ON DELETE CASCADE,
    step INTEGER DEFAULT 0,
    parent_node_id TEXT REFERENCES exploration_nodes(id) ON DELETE SET NULL,
    source_bubble_id TEXT NOT NULL,
    source_bubble_title TEXT,
    target_bubble_id TEXT NOT NULL,
    target_bubble_title TEXT,
    connection_type TEXT DEFAULT 'semantic',
    reasoning TEXT,
    edge_label TEXT,
    embedding_similarity FLOAT DEFAULT 0.0,
    llm_confidence FLOAT DEFAULT 0.0,
    combined_score FLOAT DEFAULT 0.0,
    exploration_depth INTEGER DEFAULT 1,
    is_accepted BOOLEAN DEFAULT false,
    is_rejected BOOLEAN DEFAULT false,
    is_valid BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_expl_nodes_session ON exploration_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_expl_nodes_score ON exploration_nodes(combined_score DESC);
CREATE INDEX IF NOT EXISTS idx_expl_nodes_accepted ON exploration_nodes(is_accepted);

-- ═══════════════════════════════════════════════════════════
-- 10. Discovered Edges (permanent semantic links)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS discovered_edges (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    from_idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    to_idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    edge_type TEXT DEFAULT 'discovered',
    edge_label TEXT,
    reasoning TEXT,
    confidence FLOAT DEFAULT 0.0,
    connection_type TEXT,
    exploration_session_id TEXT REFERENCES exploration_sessions(id) ON DELETE SET NULL,
    exploration_node_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(from_idea_id, to_idea_id)
);

CREATE INDEX IF NOT EXISTS idx_disc_edges_from ON discovered_edges(from_idea_id);
CREATE INDEX IF NOT EXISTS idx_disc_edges_to ON discovered_edges(to_idea_id);

-- ═══════════════════════════════════════════════════════════
-- 11. Mermaid Diagrams
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mermaid_diagrams (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title TEXT NOT NULL,
    diagram_type TEXT NOT NULL DEFAULT 'flowchart',
    content TEXT NOT NULL,
    source_idea_id TEXT REFERENCES ideas(id) ON DELETE SET NULL,
    source_shuttle_id TEXT REFERENCES shuttles(id) ON DELETE SET NULL,
    source_requirement_ids JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ,
    version INTEGER DEFAULT 1,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_mermaid_type ON mermaid_diagrams(diagram_type);
CREATE INDEX IF NOT EXISTS idx_mermaid_idea ON mermaid_diagrams(source_idea_id);

-- ═══════════════════════════════════════════════════════════
-- 12. Scheduled Tasks (APScheduler)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    action_text TEXT NOT NULL,
    execution_mode TEXT DEFAULT 'simple',
    trigger_type TEXT NOT NULL,
    trigger_config JSONB NOT NULL DEFAULT '{}',
    timezone TEXT DEFAULT 'Europe/Berlin',
    status TEXT DEFAULT 'active',
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    run_count INTEGER DEFAULT 0,
    max_runs INTEGER,
    last_result TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sched_status ON scheduled_tasks(status);
CREATE INDEX IF NOT EXISTS idx_sched_next_run ON scheduled_tasks(next_run_at);

-- ═══════════════════════════════════════════════════════════
-- 13. Flowzen: Mood/Energy Checkins
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS flowzen_checkins (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    mood TEXT NOT NULL,
    energy INTEGER NOT NULL DEFAULT 5,
    time_window TEXT DEFAULT '',
    hour INTEGER DEFAULT 0,
    source TEXT DEFAULT 'inferred',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flowzen_checkins_created ON flowzen_checkins(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 14. Flowzen: Activity Log
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS flowzen_activity (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_type TEXT NOT NULL,
    time_window TEXT DEFAULT '',
    hour INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flowzen_activity_created ON flowzen_activity(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 15. Flowzen: Diary Entries (30-min warm summaries)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS flowzen_diary (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    entry_text TEXT NOT NULL,
    mood TEXT DEFAULT 'calm',
    energy INTEGER DEFAULT 5,
    time_window TEXT DEFAULT '',
    hour INTEGER DEFAULT 0,
    intent_count INTEGER DEFAULT 0,
    category TEXT DEFAULT '',
    brain_action TEXT DEFAULT '',
    brain_reasoning TEXT DEFAULT '',
    raw_data JSONB DEFAULT '{}',
    source TEXT DEFAULT 'periodic',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flowzen_diary_created ON flowzen_diary(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 16. Videos (tracked assets)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    title TEXT DEFAULT '',
    person TEXT DEFAULT '',
    pipeline_stage TEXT DEFAULT 'raw',
    category TEXT DEFAULT 'Other',
    source_dir TEXT DEFAULT '',
    size_bytes BIGINT DEFAULT 0,
    duration_secs FLOAT DEFAULT 0.0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    tags JSONB DEFAULT '[]',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    file_modified TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_videos_person ON videos(person);
CREATE INDEX IF NOT EXISTS idx_videos_category ON videos(category);
CREATE INDEX IF NOT EXISTS idx_videos_pipeline ON videos(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 17. Video Projects
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS video_projects (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_video_projects_status ON video_projects(status);

-- ═══════════════════════════════════════════════════════════
-- 18. Video Project Persons
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS video_project_persons (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT DEFAULT '',
    raw_video_path TEXT DEFAULT '',
    voice_id TEXT DEFAULT '',
    UNIQUE(project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_video_persons_project ON video_project_persons(project_id);

-- ═══════════════════════════════════════════════════════════
-- 19. Video Pipeline Steps
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS video_pipeline_steps (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    person_name TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    output_path TEXT DEFAULT '',
    output_video_id TEXT DEFAULT '',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT DEFAULT '',
    UNIQUE(project_id, person_name, step_name)
);

CREATE INDEX IF NOT EXISTS idx_video_steps_project ON video_pipeline_steps(project_id);
CREATE INDEX IF NOT EXISTS idx_video_steps_person ON video_pipeline_steps(person_name);

-- ═══════════════════════════════════════════════════════════
-- 20. Persistent Tasks (task memory)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS persistent_tasks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    intent_type TEXT NOT NULL DEFAULT '',
    status TEXT DEFAULT 'pending',
    payload JSONB DEFAULT '{}',
    result TEXT,
    error TEXT,
    user_id TEXT DEFAULT 'default',
    session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_persistent_tasks_status ON persistent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_persistent_tasks_created ON persistent_tasks(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- 21. User Preferences
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY DEFAULT 'default',
    preferences JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════
-- 22. Schema Version (for tracking, Supabase handles migrations)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT INTO schema_version (version) VALUES (22) ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════
-- RLS: Enable on all tables, allow all for local dev (anon key)
-- ═══════════════════════════════════════════════════════════
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename NOT IN ('schema_version', 'schema_migrations')
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('CREATE POLICY "allow_all_%s" ON %I FOR ALL USING (true) WITH CHECK (true)', tbl, tbl);
    END LOOP;
END $$;

-- ═══════════════════════════════════════════════════════════
-- Realtime: Enable for tables Electron subscribes to
-- ═══════════════════════════════════════════════════════════
ALTER PUBLICATION supabase_realtime ADD TABLE ideas;
ALTER PUBLICATION supabase_realtime ADD TABLE projects;
ALTER PUBLICATION supabase_realtime ADD TABLE canvas_nodes;
ALTER PUBLICATION supabase_realtime ADD TABLE canvas_edges;
ALTER PUBLICATION supabase_realtime ADD TABLE conversation_history;
ALTER PUBLICATION supabase_realtime ADD TABLE scheduled_tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE shuttles;
ALTER PUBLICATION supabase_realtime ADD TABLE flowzen_activity;
ALTER PUBLICATION supabase_realtime ADD TABLE flowzen_diary;
ALTER PUBLICATION supabase_realtime ADD TABLE videos;
ALTER PUBLICATION supabase_realtime ADD TABLE video_projects;
ALTER PUBLICATION supabase_realtime ADD TABLE persistent_tasks;

-- ═══════════════════════════════════════════════════════════
-- pgvector: HNSW index + semantic search function
-- ═══════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_ideas_embedding ON ideas
USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE OR REPLACE FUNCTION search_ideas_by_embedding(
  query_embedding vector(384),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id text,
  title text,
  description text,
  score float,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    ideas.id,
    ideas.title,
    ideas.description,
    ideas.score,
    1 - (ideas.embedding_vector <=> query_embedding) as similarity
  FROM ideas
  WHERE ideas.embedding_vector IS NOT NULL
    AND 1 - (ideas.embedding_vector <=> query_embedding) > match_threshold
  ORDER BY ideas.embedding_vector <=> query_embedding
  LIMIT match_count;
$$;
