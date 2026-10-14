-- Additive opt-in research checkpoints. Requires baseline users table.
-- Apply only after backup and schema inspection; does not modify active indexes.
CREATE TABLE IF NOT EXISTS research_tasks (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    status VARCHAR(16) NOT NULL,
    revision INT NOT NULL DEFAULT 0,
    payload_json LONGTEXT NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_research_tasks_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
