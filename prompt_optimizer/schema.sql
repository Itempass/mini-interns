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
    workflow_step_uuid CHAR(36) NOT NULL, -- The CUSTOM_LLM step being tested
    user_id CHAR(36) NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'running', 'completed', 'failed'
    summary_report JSON, -- e.g., {"accuracy": 0.85, "total_cases": 200, "passed": 170}
    detailed_results JSON, -- Stores an array of all test cases: [{input, ground_truth, output, is_match}, ...]
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (template_uuid) REFERENCES evaluation_templates(uuid) ON DELETE CASCADE
);
