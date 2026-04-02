-- EventFix PostgreSQL Initialisierungsskript

-- Datenbank erstellen (wird automatisch durch Docker Compose erstellt)
-- CREATE DATABASE eventfix_logs;

-- Tabelle für Event Logs
CREATE TABLE IF NOT EXISTS event_logs (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    source VARCHAR(255),
    message TEXT NOT NULL,
    stack_trace TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

-- Index für schnelle Abfragen
CREATE INDEX idx_event_logs_event_id ON event_logs(event_id);
CREATE INDEX idx_event_logs_event_type ON event_logs(event_type);
CREATE INDEX idx_event_logs_severity ON event_logs(severity);
CREATE INDEX idx_event_logs_created_at ON event_logs(created_at);
CREATE INDEX idx_event_logs_processed ON event_logs(processed);

-- Tabelle für Task Logs
CREATE TABLE IF NOT EXISTS task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(255) UNIQUE NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
    agent_id VARCHAR(255),
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index für Task Logs
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_task_logs_agent_id ON task_logs(agent_id);
CREATE INDEX idx_task_logs_created_at ON task_logs(created_at);

-- Tabelle für Agent Status
CREATE TABLE IF NOT EXISTS agent_status (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR(255) UNIQUE NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('IDLE', 'BUSY', 'OFFLINE', 'ERROR')),
    current_task_id VARCHAR(255),
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index für Agent Status
CREATE INDEX idx_agent_status_agent_id ON agent_status(agent_id);
CREATE INDEX idx_agent_status_status ON agent_status(status);
CREATE INDEX idx_agent_status_last_heartbeat ON agent_status(last_heartbeat);

-- Tabelle für Fix Sessions
CREATE TABLE IF NOT EXISTS fix_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('INITIATED', 'ANALYZING', 'FIXING', 'TESTING', 'VERIFIED', 'FAILED')),
    assigned_agent_id VARCHAR(255),
    analysis_result JSONB,
    fix_result JSONB,
    test_result JSONB,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index für Fix Sessions
CREATE INDEX idx_fix_sessions_session_id ON fix_sessions(session_id);
CREATE INDEX idx_fix_sessions_event_id ON fix_sessions(event_id);
CREATE INDEX idx_fix_sessions_status ON fix_sessions(status);
CREATE INDEX idx_fix_sessions_created_at ON fix_sessions(created_at);

-- Tabelle für Test Results
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    test_id VARCHAR(255) UNIQUE NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    test_type VARCHAR(100) NOT NULL CHECK (test_type IN ('UNIT', 'INTEGRATION', 'E2E', 'PLAYWRIGHT')),
    status VARCHAR(50) NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'SKIPPED', 'ERROR')),
    test_data JSONB,
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index für Test Results
CREATE INDEX idx_test_results_test_id ON test_results(test_id);
CREATE INDEX idx_test_results_session_id ON test_results(session_id);
CREATE INDEX idx_test_results_status ON test_results(status);
CREATE INDEX idx_test_results_test_type ON test_results(test_type);

-- Trigger für automatisches Update von updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_agent_status_updated_at BEFORE UPDATE ON agent_status
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- View für aktive Agents
CREATE OR REPLACE VIEW active_agents AS
SELECT 
    agent_id,
    agent_type,
    status,
    current_task_id,
    last_heartbeat,
    metadata
FROM agent_status
WHERE status != 'OFFLINE'
  AND last_heartbeat > CURRENT_TIMESTAMP - INTERVAL '5 minutes';

-- View für offene Tasks
CREATE OR REPLACE VIEW pending_tasks AS
SELECT 
    task_id,
    task_type,
    status,
    agent_id,
    created_at
FROM task_logs
WHERE status IN ('PENDING', 'IN_PROGRESS')
ORDER BY created_at ASC;

-- View für kritische Events
CREATE OR REPLACE VIEW critical_events AS
SELECT 
    event_id,
    event_type,
    severity,
    source,
    message,
    stack_trace,
    created_at
FROM event_logs
WHERE severity IN ('ERROR', 'CRITICAL')
  AND processed = FALSE
ORDER BY created_at DESC;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO eventfix;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO eventfix;
