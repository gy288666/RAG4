-- Explicit full-corpus rebuild jobs. Requires users and migrations 002-004.
CREATE TABLE IF NOT EXISTS user_index_rebuilds (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    request_json LONGTEXT NOT NULL,
    checkpoints_json LONGTEXT NOT NULL,
    base_revision INT NOT NULL,
    attempt INT NOT NULL DEFAULT 0,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    version_id VARCHAR(64) NULL,
    error_code VARCHAR(64) NULL,
    error_document_id VARCHAR(64) NULL,
    duration_ms INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME NULL,
    INDEX ix_user_index_rebuilds_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
