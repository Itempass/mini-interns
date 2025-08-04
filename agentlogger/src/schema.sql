-- Agent Logger Database Schema
-- SQLite database for storing logs from workflows and agents.

CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    reference_string TEXT,
    log_type TEXT CHECK(log_type IN ('workflow', 'custom_agent', 'custom_llm', 'workflow_agent', 'stop_checker')) NOT NULL,
    workflow_id TEXT,
    workflow_instance_id TEXT,
    workflow_name TEXT,
    step_id TEXT,
    step_instance_id TEXT,
    step_name TEXT,
    messages TEXT, -- Storing as JSON text
    needs_review BOOLEAN DEFAULT FALSE,
    feedback TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    anonymized BOOLEAN DEFAULT FALSE,
    -- New fields for token and cost tracking
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    total_cost REAL,
    user_id TEXT,
    model TEXT
);

-- Index on start_time for chronological queries
CREATE INDEX IF NOT EXISTS idx_logs_start_time ON logs(start_time);

-- Index on type for filtering by log type
CREATE INDEX IF NOT EXISTS idx_logs_type ON logs(log_type);

-- Index on workflow_id for finding all logs for a workflow
CREATE INDEX IF NOT EXISTS idx_logs_workflow_id ON logs(workflow_id);

-- Index on workflow_instance_id for filtering
CREATE INDEX IF NOT EXISTS idx_logs_workflow_instance_id ON logs(workflow_instance_id);

-- Index on step_instance_id for filtering
CREATE INDEX IF NOT EXISTS idx_logs_step_instance_id ON logs(step_instance_id);

-- Index on user_id for filtering logs by user
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);

-- Drop the old table to ensure a clean migration
DROP TABLE IF EXISTS conversations; 