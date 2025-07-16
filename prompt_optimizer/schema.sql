-- Stores the user-defined configuration for an evaluation dataset.
CREATE TABLE IF NOT EXISTS evaluation_templates (
    uuid CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    data_source_config JSON NOT NULL, -- e.g., {"tool": "imap.get_emails", "params": {"folder": "INBOX"}}
    field_mapping_config JSON NOT NULL, -- e.g., {"input_field": "body_cleaned", "ground_truth_field": "labels"}
    cached_data JSON NOT NULL, -- A snapshot of the data fetched using the config above.
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Add an index to optimize sorting and filtering by user and last update time.
CREATE INDEX idx_eval_templates_user_updated ON evaluation_templates(user_id, updated_at DESC);

-- Tracks a specific execution of an evaluation template against a prompt.
CREATE TABLE IF NOT EXISTS evaluation_runs (
    uuid CHAR(36) PRIMARY KEY,
    template_uuid CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    original_prompt TEXT NOT NULL,
    original_model VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'running', 'completed', 'failed'
    summary_report JSON, -- e.g., {"v1_accuracy": 0.85, "v2_accuracy": 0.95}
    detailed_results JSON, -- Stores an array of all test cases and the refined prompt
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (template_uuid) REFERENCES evaluation_templates(uuid) ON DELETE CASCADE
);

-- Add an index for faster lookups of runs by user.
CREATE INDEX idx_eval_runs_user ON evaluation_runs(user_id);
