-- Agent Database Schema
-- SQLite database for storing agents and their instances

CREATE TABLE IF NOT EXISTS agents (
    uuid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_instructions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_instances (
    uuid TEXT PRIMARY KEY,
    agent_uuid TEXT NOT NULL,
    user_input TEXT,
    messages JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_uuid) REFERENCES agents (uuid)
);

-- Index on agent_uuid for quick lookup of instances for an agent
CREATE INDEX IF NOT EXISTS idx_agent_instances_agent_uuid ON agent_instances(agent_uuid);

CREATE TABLE IF NOT EXISTS triggers (
    uuid TEXT PRIMARY KEY,
    agent_uuid TEXT NOT NULL,
    function_name TEXT NOT NULL,
    rules_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_uuid) REFERENCES agents (uuid)
);

-- Index on agent_uuid for quick lookup of triggers for an agent
CREATE INDEX IF NOT EXISTS idx_triggers_agent_uuid ON triggers(agent_uuid); 