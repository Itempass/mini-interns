-- Agent Logger Database Schema
-- SQLite database for storing anonymized conversations

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    data JSON NOT NULL,  -- Complete ConversationData as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    anonymized BOOLEAN DEFAULT FALSE,
    readable_workflow_name TEXT,
    readable_instance_context TEXT
);

-- Index on created_at for chronological queries
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);

-- Index on anonymized flag for filtering
CREATE INDEX IF NOT EXISTS idx_conversations_anonymized ON conversations(anonymized);

-- Index on workflow name for filtering
CREATE INDEX IF NOT EXISTS idx_conversations_workflow_name ON conversations(readable_workflow_name); 