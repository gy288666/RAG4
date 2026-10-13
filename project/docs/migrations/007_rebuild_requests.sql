-- Additive creation deduplication. Requires 005_index_rebuilds.sql.
CREATE TABLE IF NOT EXISTS index_rebuild_requests (
    user_id INT NOT NULL,
    request_key VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    PRIMARY KEY (user_id, request_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES user_index_rebuilds(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
