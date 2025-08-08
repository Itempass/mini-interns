CREATE TABLE IF NOT EXISTS `vector_databases` (
    `uuid` BINARY(16) PRIMARY KEY,
    `user_id` BINARY(16) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `type` ENUM('internal', 'external') NOT NULL,
    `provider` VARCHAR(255) NOT NULL,
    `settings` JSON,
    `status` VARCHAR(50),
    `error_message` TEXT,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_vector_databases_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; 