-- EventFix Team Database Initialization Script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create tables

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    title TEXT NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_to VARCHAR(100),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3
);

-- Create indexes for tasks
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_type ON tasks(task_type);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
CREATE INDEX idx_tasks_metadata ON tasks USING GIN(metadata);

-- Code changes table
CREATE TABLE IF NOT EXISTS code_changes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    change_type VARCHAR(20) NOT NULL,
    old_content TEXT,
    new_content TEXT,
    diff TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMP WITH TIME ZONE,
    rollback_data JSONB
);

-- Create indexes for code_changes
CREATE INDEX idx_code_changes_task_id ON code_changes(task_id);
CREATE INDEX idx_code_changes_file_path ON code_changes(file_path);
CREATE INDEX idx_code_changes_applied ON code_changes(applied);

-- Fix attempts table
CREATE TABLE IF NOT EXISTS fix_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    strategy TEXT,
    changes JSONB DEFAULT '[]',
    result VARCHAR(50),
    error_message TEXT,
    logs TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    success BOOLEAN DEFAULT FALSE
);

-- Create indexes for fix_attempts
CREATE INDEX idx_fix_attempts_task_id ON fix_attempts(task_id);
CREATE INDEX idx_fix_attempts_success ON fix_attempts(success);
CREATE INDEX idx_fix_attempts_agent_type ON fix_attempts(agent_type);

-- Migration records table
CREATE TABLE IF NOT EXISTS migration_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    migration_name TEXT NOT NULL,
    from_version TEXT,
    to_version TEXT,
    status VARCHAR(50) NOT NULL,
    changes JSONB DEFAULT '[]',
    rollback_script TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

-- Create indexes for migration_records
CREATE INDEX idx_migration_records_task_id ON migration_records(task_id);
CREATE INDEX idx_migration_records_status ON migration_records(status);

-- Test results table
CREATE TABLE IF NOT EXISTS test_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    test_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    duration_ms INTEGER,
    error_message TEXT,
    logs TEXT,
    screenshots TEXT[],
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for test_results
CREATE INDEX idx_test_results_task_id ON test_results(task_id);
CREATE INDEX idx_test_results_status ON test_results(status);
CREATE INDEX idx_test_results_type ON test_results(test_type);

-- Agent logs table
CREATE TABLE IF NOT EXISTS agent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL,
    log_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for agent_logs
CREATE INDEX idx_agent_logs_task_id ON agent_logs(task_id);
CREATE INDEX idx_agent_logs_agent_type ON agent_logs(agent_type);
CREATE INDEX idx_agent_logs_level ON agent_logs(log_level);
CREATE INDEX idx_agent_logs_created_at ON agent_logs(created_at);

-- Docker containers table
CREATE TABLE IF NOT EXISTS docker_containers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    container_id TEXT NOT NULL,
    container_name TEXT,
    image_name TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    ports TEXT[],
    environment JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE,
    logs TEXT
);

-- Create indexes for docker_containers
CREATE INDEX idx_docker_containers_task_id ON docker_containers(task_id);
CREATE INDEX idx_docker_containers_status ON docker_containers(status);
CREATE INDEX idx_docker_containers_container_id ON docker_containers(container_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for tasks table
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data (optional)
INSERT INTO tasks (task_type, status, priority, title, description, metadata)
VALUES 
    ('code_write', 'pending', 1, 'Initial Setup', 'Setup EventFix Team infrastructure', '{"test": true}'),
    ('fix', 'pending', 2, 'Bug Fix Example', 'Example bug fix task', '{"bug_id": "BUG-001"}')
ON CONFLICT DO NOTHING;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO eventfix_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO eventfix_user;
