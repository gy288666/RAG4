-- Additive Phase 2 preparation tables. Run against the selected existing DB.
-- Does not modify documents, vectors, runtime settings or active versions.
CREATE TABLE IF NOT EXISTS document_chunk_sets (
    id VARCHAR(80) NOT NULL PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    payload_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_document_chunk_sets_document_id (document_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_index_jobs (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    kind VARCHAR(32) NOT NULL DEFAULT 'prepare_chunks',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    source_sha256 VARCHAR(64) NOT NULL,
    config_json TEXT NOT NULL,
    chunk_set_id VARCHAR(80) NULL,
    error_code VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    duration_ms INT NULL,
    CONSTRAINT uq_index_job_request UNIQUE (user_id, idempotency_key),
    INDEX ix_document_index_jobs_document_id (document_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
