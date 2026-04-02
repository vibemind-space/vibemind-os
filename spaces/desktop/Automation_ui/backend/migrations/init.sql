-- TRAE Backend - Initial Database Schema
-- Creates tables for desktop streaming, configurations, and automation
-- This file is executed on first PostgreSQL container startup

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Live Desktop Configurations
-- ============================================
CREATE TABLE IF NOT EXISTS live_desktop_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    configuration JSONB DEFAULT '{}'::jsonb NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    created_by VARCHAR(255),
    tags JSONB DEFAULT '[]'::jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_configs_category ON live_desktop_configs(category);
CREATE INDEX IF NOT EXISTS idx_live_configs_active ON live_desktop_configs(is_active);
CREATE INDEX IF NOT EXISTS idx_live_configs_updated ON live_desktop_configs(updated_at DESC);

-- ============================================
-- Active Desktop Clients
-- ============================================
CREATE TABLE IF NOT EXISTS active_desktop_clients (
    client_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    monitors JSONB DEFAULT '[]'::jsonb NOT NULL,
    capabilities JSONB DEFAULT '{}'::jsonb NOT NULL,
    user_id VARCHAR(255),
    hostname VARCHAR(255),
    is_streaming BOOLEAN DEFAULT FALSE NOT NULL,
    last_ping TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_active_clients_last_ping ON active_desktop_clients(last_ping);
CREATE INDEX IF NOT EXISTS idx_active_clients_streaming ON active_desktop_clients(is_streaming);

-- ============================================
-- Desktop Commands Queue
-- ============================================
CREATE TABLE IF NOT EXISTS desktop_commands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    desktop_client_id VARCHAR(255) NOT NULL,
    command_type VARCHAR(100) NOT NULL,
    command_data JSONB DEFAULT '{}'::jsonb NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    idempotency_key VARCHAR(255) UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_desktop_commands_client_status ON desktop_commands(desktop_client_id, status);
CREATE INDEX IF NOT EXISTS idx_desktop_commands_created ON desktop_commands(created_at);
CREATE INDEX IF NOT EXISTS idx_desktop_commands_pending ON desktop_commands(desktop_client_id, status, created_at)
    WHERE status = 'pending';

-- ============================================
-- Workflows
-- ============================================
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    nodes JSONB DEFAULT '[]'::jsonb NOT NULL,
    connections JSONB DEFAULT '[]'::jsonb NOT NULL,
    variables JSONB DEFAULT '{}'::jsonb NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_workflows_active ON workflows(is_active);
CREATE INDEX IF NOT EXISTS idx_workflows_updated ON workflows(updated_at DESC);

-- ============================================
-- Workflow Executions
-- ============================================
CREATE TABLE IF NOT EXISTS workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    node_results JSONB DEFAULT '{}'::jsonb NOT NULL,
    variables JSONB DEFAULT '{}'::jsonb NOT NULL,
    logs JSONB DEFAULT '[]'::jsonb NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow ON workflow_executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_created ON workflow_executions(created_at DESC);

-- ============================================
-- Helper Functions
-- ============================================

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for auto-updating timestamps
DROP TRIGGER IF EXISTS update_live_desktop_configs_updated_at ON live_desktop_configs;
CREATE TRIGGER update_live_desktop_configs_updated_at
    BEFORE UPDATE ON live_desktop_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_active_desktop_clients_updated_at ON active_desktop_clients;
CREATE TRIGGER update_active_desktop_clients_updated_at
    BEFORE UPDATE ON active_desktop_clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_workflows_updated_at ON workflows;
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Cleanup Functions
-- ============================================

-- Function to clean up stale desktop clients (not pinged in last 2 minutes)
CREATE OR REPLACE FUNCTION cleanup_stale_desktop_clients()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM active_desktop_clients
    WHERE last_ping < NOW() - INTERVAL '2 minutes';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old commands (older than 30 minutes)
CREATE OR REPLACE FUNCTION cleanup_old_desktop_commands()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM desktop_commands
    WHERE created_at < NOW() - INTERVAL '30 minutes'
    AND status IN ('completed', 'failed');

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Sample Data (Development Only)
-- ============================================
-- Insert a sample configuration for testing
INSERT INTO live_desktop_configs (name, description, category, configuration, is_active, tags)
VALUES (
    'Default Streaming Config',
    'Standard configuration for desktop streaming',
    'streaming',
    '{"fps": 30, "quality": 80, "scale": 1.0, "format": "jpeg"}'::jsonb,
    true,
    '["default", "streaming"]'::jsonb
) ON CONFLICT DO NOTHING;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'TRAE Backend database initialized successfully!';
END $$;
