-- Recovery history and unique successors. Requires 005_index_rebuilds.sql.
CREATE TABLE IF NOT EXISTS index_rebuild_recoveries (
    source_task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    target_task_id VARCHAR(64) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_index_rebuild_recoveries_user_id (user_id),
    FOREIGN KEY (source_task_id) REFERENCES user_index_rebuilds(id) ON DELETE CASCADE,
    FOREIGN KEY (target_task_id) REFERENCES user_index_rebuilds(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
