-- Additive candidate builds; prerequisite: 002_chunk_preparation.sql.
CREATE TABLE IF NOT EXISTS document_index_builds (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    chunk_set_id VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    index_version VARCHAR(64) NOT NULL UNIQUE,
    embedding_spec_json TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    manifest_json TEXT NULL,
    error_code VARCHAR(64) NULL,
    error_stage VARCHAR(32) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    duration_ms INT NULL,
    CONSTRAINT uq_index_build_request UNIQUE (user_id, idempotency_key),
    INDEX ix_document_index_builds_document_id (document_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_set_id) REFERENCES document_chunk_sets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
