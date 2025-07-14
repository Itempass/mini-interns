-- Workflow Engine Database Schema
-- MySQL database for storing workflow definitions, instances, and related data.

-- For UUIDs, we use BINARY(16) for efficient storage and indexing.
-- The application layer will be responsible for converting between string and binary representations.

CREATE TABLE IF NOT EXISTS `workflows` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT,
    `is_active` BOOLEAN DEFAULT TRUE,
    `trigger_uuid` BINARY(16),
    `steps` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_workflows_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_steps` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `type` VARCHAR(50) NOT NULL COMMENT 'Discriminator: custom_llm, custom_agent, stop_checker',
    `details` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_workflow_steps_user_id` (`user_id`),
    INDEX `idx_workflow_steps_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `triggers` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `workflow_uuid` BINARY(16) NOT NULL,
    `details` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_triggers_user_id` (`user_id`),
    INDEX `idx_triggers_workflow_uuid` (`workflow_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_instances` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `workflow_definition_uuid` BINARY(16) NOT NULL,
    `status` VARCHAR(50) NOT NULL,
    `trigger_output` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_workflow_instances_user_id` (`user_id`),
    INDEX `idx_workflow_instances_workflow_definition_uuid` (`workflow_definition_uuid`),
    INDEX `idx_workflow_instances_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_step_instances` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `workflow_instance_uuid` BINARY(16) NOT NULL,
    `step_definition_uuid` BINARY(16) NOT NULL,
    `status` VARCHAR(50) NOT NULL,
    `started_at` TIMESTAMP NULL,
    `finished_at` TIMESTAMP NULL,
    `output_id` BINARY(16),
    `output` JSON,
    `details` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_workflow_step_instances_user_id` (`user_id`),
    INDEX `idx_workflow_step_instances_workflow_instance_uuid` (`workflow_instance_uuid`),
    INDEX `idx_workflow_step_instances_step_definition_uuid` (`step_definition_uuid`),
    INDEX `idx_workflow_step_instances_output_id` (`output_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `step_outputs` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `raw_data` JSON,
    `summary` TEXT,
    `markdown_representation` TEXT,
    `data_schema` JSON,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_step_outputs_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; 