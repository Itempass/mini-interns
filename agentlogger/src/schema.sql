-- Agent Logger Database Schema
-- SQLite database for storing anonymized conversations

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    data JSON NOT NULL,  -- Complete ConversationData as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    anonymized BOOLEAN DEFAULT FALSE
);

-- Index on created_at for chronological queries
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);

-- Index on anonymized flag for filtering
CREATE INDEX IF NOT EXISTS idx_conversations_anonymized ON conversations(anonymized); 