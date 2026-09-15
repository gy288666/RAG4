-- =============================================================
-- RAG 学术知识引擎 — 数据库初始化 DDL 脚本 (v1.4 模型版本版)
-- 数据库名称：rag_high
-- 数据库版本：MySQL 5.7+ / 8.0
-- 文档来源：requirements_document.md v1.1 + api_document.md v1.0
-- 更新日期：2026-09-14
-- -------------------------------------------------------------
-- 变更说明 (v1.4，RAG4 模型微调接入)：
--   system_configs 新增 Embedding/Reranker 的 provider、version、local_path。
--   embedding.version 同时作为向量索引命名空间，避免不同模型语义空间混写。
-- -------------------------------------------------------------
-- 变更说明 (v1.3，接入真实模型联调后新增)：
--   1. system_configs 新增 llm.aux_model：辅助任务（问题改写、标题生成）
--      使用的小模型。主模型为推理型（先输出 reasoning_content 思考内容）时，
--      这类短任务会因思考耗时频繁超时降级，必须可单独配置。
--   2. system_configs 新增 rerank.model：Rerank 模型名各服务商取值不同
--      （Cohere: rerank-multilingual-v3.0；硅基流动: BAAI/bge-reranker-v2-m3），
--      原先硬编码导致换服务商后精排必然失败。
-- -------------------------------------------------------------
-- 变更说明 (v1.2，实现阶段新增，详见 docs/db_changelog.md)：
--   1. usage_logs 新增 ref_id 字段：关联业务对象 ID（如 doc_id），
--      使管理后台 GET /api/v1/admin/stats 的「OCR 失败队列」能够
--      回溯到具体文档的 doc_id 与文件名。
--   2. system_configs 新增 4 条默认配置：
--      embedding.base_url / embedding.api_key（Embedding 服务独立配置，
--      留空则复用 LLM 的 Base URL 与 Key）、
--      retrieval.top_n（密集检索候选数 Top-N）、
--      retrieval.history_rounds（多轮对话历史轮数上限，PRD 4.3.3）。
-- -------------------------------------------------------------
-- 变更说明 (v1.1)：
--   [S-2] users 表新增 token_version 字段，支持 JWT 主动失效
--   [M-4] password_reset_requests 表新增 last_request_at，支持应用层频率限制
--   [M-1] documents 表新增 updated_at 字段，前端可判断状态是否卡滞
--   [I-1] documents.file_size 由 INT 改为 BIGINT，支持大文件扩展
--   [I-4] 新增 usage_logs 运行日志表，支持管理后台监控统计
--   [S-1] system_configs 表注释更新，说明 API Key 存密文
-- =============================================================

-- -----------------------------------------------
-- 0. 重建数据库（开发环境清理重建）
--    生产环境执行前请去掉 DROP DATABASE 语句！
-- -----------------------------------------------
DROP DATABASE IF EXISTS `rag_high`;

CREATE DATABASE `rag_high`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE `rag_high`;

-- -----------------------------------------------
-- 1. 用户表 users
--    role 值：'user' | 'admin'
--    status 值：1=启用, 0=禁用
--    [S-2] token_version：密码重置时 +1，使旧 JWT 立即失效
-- -----------------------------------------------
CREATE TABLE `users` (
    `id`             INT             NOT NULL AUTO_INCREMENT COMMENT '用户唯一主键（自增）',
    `email`          VARCHAR(128)    NOT NULL                COMMENT '注册邮箱（唯一索引）',
    `password_hash`  VARCHAR(255)    NOT NULL                COMMENT 'bcrypt 单向哈希加密后的密码',
    `role`           VARCHAR(32)     NOT NULL DEFAULT 'user' COMMENT '角色：user | admin',
    `status`         TINYINT         NOT NULL DEFAULT 1      COMMENT '账号状态：1=启用, 0=禁用',
    `token_version`  INT             NOT NULL DEFAULT 0      COMMENT 'JWT 版本号：密码重置时 +1，用于主动使旧 Token 失效 [S-2]',
    `last_login_at`  DATETIME                 DEFAULT NULL   COMMENT '最近一次成功登录时间（管理列表展示用）',
    `created_at`     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    `updated_at`     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '信息最后修改时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_users_email` (`email`),
    KEY `idx_users_role` (`role`),
    KEY `idx_users_status` (`status`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户账号表';


-- -----------------------------------------------
-- 2. 密码重置申请记录表 password_reset_requests
--    流程 B：用户前台提交 → 管理员后台处理
--    [M-4] 新增 last_request_at 支持应用层 10 分钟频率限制
--    应用层检查逻辑：
--      SELECT * FROM password_reset_requests
--        WHERE email=? AND is_handled=0
--          AND last_request_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)
--      LIMIT 1;
--      若有记录则拒绝，返回 400。
-- -----------------------------------------------
CREATE TABLE `password_reset_requests` (
    `id`               INT          NOT NULL AUTO_INCREMENT COMMENT '记录主键（自增）',
    `email`            VARCHAR(128) NOT NULL                COMMENT '申请重置密码的用户邮箱',
    `is_handled`       TINYINT      NOT NULL DEFAULT 0      COMMENT '是否已处理：0=待处理, 1=已完成',
    `last_request_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近一次提交时间（用于应用层频率限制）[M-4]',
    `requested_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次提交申请时间',
    `handled_at`       DATETIME              DEFAULT NULL   COMMENT '管理员处理完成时间',
    PRIMARY KEY (`id`),
    KEY `idx_reset_email_handled` (`email`, `is_handled`),
    KEY `idx_reset_last_request` (`last_request_at`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='密码重置申请记录表（流程B，管理员后台处理）';


-- -----------------------------------------------
-- 3. 文档元数据表 documents
--    [M-1] 新增 updated_at：解析状态流转时更新，前端可判断处理是否卡住
--    [I-1] file_size 改为 BIGINT：支持超大文件未来扩展
--    status 状态机：pending → parsing → vectorizing → ready / failed
-- -----------------------------------------------
CREATE TABLE `documents` (
    `id`          VARCHAR(64)  NOT NULL                   COMMENT '文档唯一标识（UUID）',
    `user_id`     INT          NOT NULL                   COMMENT '所属用户ID（外键→users.id）',
    `file_name`   VARCHAR(255) NOT NULL                   COMMENT '原始上传文件名',
    `file_size`   BIGINT       NOT NULL DEFAULT 0         COMMENT '文件大小（字节），BIGINT 支持大文件 [I-1]',
    `local_path`  VARCHAR(512) NOT NULL                   COMMENT '服务器本地物理存储路径（如 /data/uploads/{user_id}/xxx.pdf）',
    `status`      VARCHAR(32)  NOT NULL DEFAULT 'pending' COMMENT '解析状态：pending|parsing|vectorizing|ready|failed',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '状态最后更新时间（前端轮询判断是否卡住）[M-1]',
    PRIMARY KEY (`id`),
    KEY `idx_documents_user_id` (`user_id`),
    KEY `idx_documents_status` (`status`),
    KEY `idx_documents_updated_at` (`updated_at`),
    CONSTRAINT `fk_documents_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户上传文档的元数据与解析状态表';


-- -----------------------------------------------
-- 4. 对话会话表 chat_sessions
--    is_deleted：0=正常, 1=逻辑删除
-- -----------------------------------------------
CREATE TABLE `chat_sessions` (
    `id`         VARCHAR(64)  NOT NULL                 COMMENT '会话UUID（主键）',
    `user_id`    INT          NOT NULL                 COMMENT '所属用户ID（外键→users.id）',
    `title`      VARCHAR(255) NOT NULL DEFAULT '新对话' COMMENT '会话标题（LLM自动生成或用户手动修改）',
    `is_deleted` TINYINT      NOT NULL DEFAULT 0       COMMENT '逻辑删除标记：0=未删除, 1=已删除',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '会话创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '会话最后活跃时间（按此排序列表）',
    PRIMARY KEY (`id`),
    KEY `idx_sessions_user_id` (`user_id`),
    KEY `idx_sessions_is_deleted` (`is_deleted`),
    KEY `idx_sessions_updated_at` (`updated_at`),
    CONSTRAINT `fk_sessions_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='问答对话会话表';


-- -----------------------------------------------
-- 5. 对话消息记录表 chat_messages
--    role 值：'user' | 'assistant'
--    citations：JSON 引用列表（仅 assistant 消息填充）
--    enable_rag=false 时 citations 字段值为 NULL
-- -----------------------------------------------
CREATE TABLE `chat_messages` (
    `id`         VARCHAR(64)  NOT NULL              COMMENT '消息唯一ID（UUID）',
    `session_id` VARCHAR(64)  NOT NULL              COMMENT '所属会话ID（外键→chat_sessions.id）',
    `role`       VARCHAR(32)  NOT NULL              COMMENT '消息角色：user | assistant',
    `content`    MEDIUMTEXT   NOT NULL              COMMENT '消息正文（MEDIUMTEXT 最大 16MB，适应长篇 LLM 回答）',
    `citations`  JSON                  DEFAULT NULL COMMENT '引用溯源元数据 JSON 数组（enable_rag=false 时为 NULL）',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息生成时间',
    PRIMARY KEY (`id`),
    KEY `idx_messages_session_id` (`session_id`),
    KEY `idx_messages_role` (`role`),
    KEY `idx_messages_created_at` (`created_at`),
    CONSTRAINT `fk_messages_session_id`
        FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='对话消息记录表（包含引用溯源JSON）';


-- -----------------------------------------------
-- 6. 系统配置表 system_configs
--    [S-1] API Key 字段在应用层 AES-256 加密后写入，存密文
--    管理员后台 GET 接口返回脱敏掩码，不返回明文
-- -----------------------------------------------
CREATE TABLE `system_configs` (
    `config_key`   VARCHAR(128) NOT NULL            COMMENT '配置项唯一 Key（主键）',
    `config_value` TEXT         NOT NULL            COMMENT '配置值（API Key 类字段存 AES-256 密文）[S-1]',
    `description`  VARCHAR(255)          DEFAULT '' COMMENT '配置项的中文说明',
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近修改时间',
    PRIMARY KEY (`config_key`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='系统全局动态配置表（LLM、Rerank、Embedding、切片参数，API Key 密文存储）';


-- -----------------------------------------------
-- 7. 运行日志表 usage_logs
--    [I-4] 支持管理后台运行监控统计：
--          调用次数、Token 消耗量、OCR 失败队列等
-- -----------------------------------------------
CREATE TABLE `usage_logs` (
    `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '日志主键（自增，BIGINT 适配高频写入）',
    `user_id`       INT                   DEFAULT NULL   COMMENT '触发操作的用户ID（NULL 表示系统内部调用）',
    `event_type`    VARCHAR(64)  NOT NULL               COMMENT '事件类型：llm_call | rerank_call | ocr_call | vector_search',
    `tokens_used`   INT          NOT NULL DEFAULT 0      COMMENT '大模型 Token 消耗量（仅 llm_call 有值）',
    `duration_ms`   INT          NOT NULL DEFAULT 0      COMMENT '本次操作耗时（毫秒）',
    `is_success`    TINYINT      NOT NULL DEFAULT 1      COMMENT '是否成功：1=成功, 0=失败',
    `error_message` VARCHAR(512)          DEFAULT NULL   COMMENT '失败时的错误信息摘要',
    `ref_id`        VARCHAR(64)           DEFAULT NULL   COMMENT '关联业务对象ID（如 documents.id），用于 OCR 失败队列回溯 [v1.2]',
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '日志记录时间',
    PRIMARY KEY (`id`),
    KEY `idx_usage_user_id` (`user_id`),
    KEY `idx_usage_event_type` (`event_type`),
    KEY `idx_usage_is_success` (`is_success`),
    KEY `idx_usage_ref_id` (`ref_id`),
    KEY `idx_usage_created_at` (`created_at`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='系统运行日志表（管理后台监控统计数据来源）';


-- -----------------------------------------------
-- 8. system_configs 初始化默认配置数据
--    注意：API Key 字段默认为空，由管理员后台配置
--    生产环境中 API Key 值须经应用层 AES-256 加密后写入
-- -----------------------------------------------
INSERT INTO `system_configs` (`config_key`, `config_value`, `description`) VALUES
    ('llm.base_url',       'https://api.deepseek.com',                       'LLM API 服务的 Base URL'),
    ('llm.api_key',        '',                                                'LLM API 调用密钥（AES-256密文，生产环境通过管理后台配置）'),
    ('llm.model',          'deepseek-ai/DeepSeek-V4-Flash',                  '默认使用的 LLM 模型名称'),
    ('rerank.api_url',     'https://api.cohere.com/v1/rerank',               '云端 Rerank API 终结点'),
    ('rerank.api_key',     '',                                                'Rerank API 调用密钥（AES-256密文，生产环境通过管理后台配置）'),
    ('rerank.top_k',       '5',                                               'Rerank 精排后保留的 Top-K 文本片段数量'),
    ('chunking.chunk_size','600',                                             '文档切片大小（字符数），管理员可动态调整测试'),
    ('chunking.overlap',   '60',                                              '相邻切片的重叠字符数，避免跨块信息丢失'),
    ('embedding.model',    'Qwen/Qwen3-Embedding-8B',                        '文本向量化使用的 Embedding 模型名称（管理后台可修改）'),
    -- 以下 4 项为 v1.2 实现阶段新增
    ('embedding.base_url', '',                                                'Embedding 服务 Base URL（留空则复用 llm.base_url）'),
    ('embedding.api_key',  '',                                                'Embedding API 调用密钥（AES-256密文，留空则复用 llm.api_key）'),
    ('retrieval.top_n',    '20',                                              '密集检索阶段返回的候选片段数量 Top-N'),
    ('retrieval.history_rounds', '5',                                         '多轮对话携带的历史轮数上限（PRD 4.3.3）'),
    -- 以下 2 项为 v1.3 新增（真实模型联调后补充）
    ('llm.aux_model',      '',                                                '辅助任务（问题改写、标题生成）模型；留空复用主模型。主模型为推理型时建议单独配置小模型'),
    ('rerank.model',       'BAAI/bge-reranker-v2-m3',                        'Rerank 模型名称（各服务商取值不同）'),
    -- 以下 6 项为 v1.4 新增（本地微调模型与版本化索引）
    ('rerank.provider',    'remote',                                          'Rerank Adapter：remote 或 local'),
    ('rerank.version',     'baseline',                                        'Rerank 模型版本，用于实验追踪'),
    ('rerank.local_path',  '',                                                '本地微调 Reranker 目录；留空时使用模型名称'),
    ('embedding.provider', 'remote',                                          'Embedding Adapter：remote 或 local'),
    ('embedding.version',  'baseline',                                        'Embedding 模型版本，同时作为向量索引命名空间'),
    ('embedding.local_path','',                                                '本地微调 Embedding 目录；留空时使用模型名称')
ON DUPLICATE KEY UPDATE `config_value` = VALUES(`config_value`);


-- -----------------------------------------------
-- 完成确认
-- -----------------------------------------------
SELECT CONCAT(
    '数据库 rag_high 建表完成 (v1.4)。共 7 张表：',
    'users, password_reset_requests, documents, chat_sessions, chat_messages, system_configs, usage_logs。',
    ' system_configs 已写入 21 条默认配置。'
) AS `初始化结果`;
