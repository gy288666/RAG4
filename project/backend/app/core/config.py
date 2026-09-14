"""应用级静态配置（来自环境变量 / .env 文件）。

注意区分两类配置：
- 本文件：进程启动即固定的基础设施配置（数据库地址、密钥、路径、限额）。
- ``app.services.config_service``：存放在 MySQL ``system_configs`` 表中、
  管理员可在后台热修改并立即全局生效的业务配置（LLM / Rerank / 切片参数等）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", str(BASE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    APP_NAME: str = "RAG 学术知识引擎"
    APP_VERSION: str = "1.1.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ---------- 数据库 ----------
    # 生产：mysql+pymysql://user:pwd@host:3306/rag_high?charset=utf8mb4
    # 开发/测试：sqlite:///./data/rag_high.db
    DATABASE_URL: str = "mysql+pymysql://root:root@127.0.0.1:3306/rag_high?charset=utf8mb4"
    DB_ECHO: bool = False

    # ---------- 安全 ----------
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    # PRD 4.1.1：JWT 默认有效期 7 天
    JWT_EXPIRE_SECONDS: int = 7 * 24 * 3600
    # system_configs 中 API Key 的 AES-256 加密密钥；留空则回退使用 SECRET_KEY 派生
    CONFIG_ENCRYPTION_KEY: str = ""

    # ---------- CORS ----------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- 文件存储 ----------
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    CHROMA_DIR: str = str(BASE_DIR / "data" / "chroma")
    # PRD 4.2.2：单文件最大 50MB，单次最多 10 个
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    MAX_FILES_PER_UPLOAD: int = 10
    ALLOWED_EXTENSIONS: str = ".pdf,.docx,.txt,.md,.markdown"

    # ---------- 异步解析线程池 ----------
    WORKER_THREADS: int = 4

    # ---------- RAG 超时（秒），对应 PRD 4.3.3 [M-6] ----------
    QUERY_REWRITE_TIMEOUT: float = 3.0
    RERANK_TIMEOUT: float = 3.0
    LLM_TIMEOUT: float = 30.0
    EMBEDDING_TIMEOUT: float = 30.0

    # ---------- 密码重置频率限制 [M-4] ----------
    RESET_REQUEST_INTERVAL_MINUTES: int = 10

    # ---------- 离线开发开关 ----------
    # 置为 true 时，Embedding / LLM / Rerank 使用本地确定性 Mock 实现，
    # 便于在没有外部 API Key 的环境下跑通全链路与自动化测试。
    # 严禁在生产环境开启。
    DEV_MOCK_AI: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
