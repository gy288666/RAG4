"""系统动态配置服务（``system_configs`` 表）。

PRD 4.5.2：管理员在后台修改 LLM / Rerank / Embedding / 切片参数后立即全局生效。
实现方式：进程内带 TTL 的缓存 + 写入时主动失效，避免每次问答都查库。

[S-1] API Key 类配置以 AES-256 密文存储，``get_secret`` 解密后仅在内存中使用，
``masked`` 输出脱敏掩码供管理后台展示。
"""

from __future__ import annotations

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.system_config import SystemConfig

# ---------- 配置键常量 ----------
LLM_BASE_URL = "llm.base_url"
LLM_API_KEY = "llm.api_key"
LLM_MODEL = "llm.model"
LLM_AUX_MODEL = "llm.aux_model"

RERANK_API_URL = "rerank.api_url"
RERANK_API_KEY = "rerank.api_key"
RERANK_TOP_K = "rerank.top_k"
RERANK_MODEL = "rerank.model"
RERANK_PROVIDER = "rerank.provider"
RERANK_VERSION = "rerank.version"
RERANK_LOCAL_PATH = "rerank.local_path"

EMBEDDING_MODEL = "embedding.model"
EMBEDDING_BASE_URL = "embedding.base_url"
EMBEDDING_API_KEY = "embedding.api_key"
EMBEDDING_PROVIDER = "embedding.provider"
EMBEDDING_VERSION = "embedding.version"
EMBEDDING_LOCAL_PATH = "embedding.local_path"

CHUNK_SIZE = "chunking.chunk_size"
CHUNK_OVERLAP = "chunking.overlap"

RETRIEVAL_TOP_N = "retrieval.top_n"
HISTORY_ROUNDS = "retrieval.history_rounds"

#: 需要 AES-256 静态加密的配置键 [S-1]
SECRET_KEYS: frozenset[str] = frozenset({LLM_API_KEY, RERANK_API_KEY, EMBEDDING_API_KEY})

#: 默认值与说明；缺失的键在首次读取时自动补齐入库
DEFAULTS: dict[str, tuple[str, str]] = {
    LLM_BASE_URL: ("https://api.deepseek.com", "LLM API 服务的 Base URL"),
    LLM_API_KEY: ("", "LLM API 调用密钥（AES-256 密文）"),
    LLM_MODEL: ("deepseek-ai/DeepSeek-V4-Flash", "默认使用的 LLM 模型名称"),
    LLM_AUX_MODEL: (
        "",
        "辅助任务（问题改写、标题生成）使用的小模型；留空则复用主模型。"
        "主模型为推理型时强烈建议单独配置，否则思考耗时会导致这两项频繁超时降级",
    ),
    RERANK_API_URL: ("https://api.cohere.com/v1/rerank", "云端 Rerank API 终结点"),
    RERANK_API_KEY: ("", "Rerank API 调用密钥（AES-256 密文）"),
    RERANK_TOP_K: ("5", "Rerank 精排后保留的 Top-K 文本片段数量"),
    RERANK_MODEL: ("BAAI/bge-reranker-v2-m3", "Rerank 模型名称（各服务商取值不同）"),
    RERANK_PROVIDER: ("remote", "Rerank Adapter：remote 或 local"),
    RERANK_VERSION: ("baseline", "Rerank 模型版本，用于实验追踪"),
    RERANK_LOCAL_PATH: ("", "本地微调 Reranker 目录；留空时使用模型名称"),
    EMBEDDING_MODEL: ("Qwen/Qwen3-Embedding-8B", "文本向量化使用的 Embedding 模型名称"),
    EMBEDDING_BASE_URL: ("", "Embedding 服务 Base URL（留空则复用 LLM Base URL）"),
    EMBEDDING_API_KEY: ("", "Embedding API 调用密钥（AES-256 密文，留空则复用 LLM Key）"),
    EMBEDDING_PROVIDER: ("remote", "Embedding Adapter：remote 或 local"),
    EMBEDDING_VERSION: ("baseline", "Embedding 模型版本，同时作为向量索引命名空间"),
    EMBEDDING_LOCAL_PATH: ("", "本地微调 Embedding 目录；留空时使用模型名称"),
    CHUNK_SIZE: ("600", "文档切片大小（字符数）"),
    CHUNK_OVERLAP: ("60", "相邻切片的重叠字符数"),
    RETRIEVAL_TOP_N: ("20", "向量密集检索的候选片段数量 Top-N"),
    HISTORY_ROUNDS: ("5", "多轮对话携带的历史轮数上限"),
}

_CACHE_TTL_SECONDS = 5.0

_lock = threading.RLock()
_cache: dict[str, str] = {}
_cache_at: float = 0.0


def invalidate_cache() -> None:
    global _cache_at
    with _lock:
        _cache.clear()
        _cache_at = 0.0


def _load_all(db: Session) -> dict[str, str]:
    """读取全部配置（带 TTL 缓存），并自动补齐缺失的默认键。"""
    global _cache_at
    with _lock:
        if _cache and (time.monotonic() - _cache_at) < _CACHE_TTL_SECONDS:
            return dict(_cache)

    rows = db.execute(select(SystemConfig)).scalars().all()
    values = {row.config_key: row.config_value for row in rows}

    missing = [k for k in DEFAULTS if k not in values]
    if missing:
        for key in missing:
            default_value, description = DEFAULTS[key]
            db.add(
                SystemConfig(config_key=key, config_value=default_value, description=description)
            )
            values[key] = default_value
        db.commit()

    with _lock:
        _cache.clear()
        _cache.update(values)
        _cache_at = time.monotonic()
    return dict(values)


def get(db: Session, key: str, default: str | None = None) -> str:
    values = _load_all(db)
    if key in values:
        return values[key]
    return default if default is not None else DEFAULTS.get(key, ("", ""))[0]


def get_int(db: Session, key: str, default: int) -> int:
    try:
        return int(str(get(db, key)).strip())
    except (TypeError, ValueError):
        return default


def get_secret(db: Session, key: str) -> str:
    """读取并解密敏感配置，返回明文（仅限服务端内存中使用）。"""
    return decrypt_secret(get(db, key, ""))


def set_value(db: Session, key: str, value: str, *, commit: bool = True) -> None:
    """写入配置；敏感键自动 AES-256 加密后落库 [S-1]。"""
    stored = encrypt_secret(value) if key in SECRET_KEYS else str(value)
    row = db.get(SystemConfig, key)
    if row is None:
        row = SystemConfig(
            config_key=key, config_value=stored, description=DEFAULTS.get(key, ("", ""))[1]
        )
        db.add(row)
    else:
        row.config_value = stored
    if commit:
        db.commit()
    invalidate_cache()


def masked(db: Session, key: str) -> str:
    """返回脱敏掩码，绝不返回明文 [S-1]。"""
    return mask_secret(get_secret(db, key))


# ------------------------------------------------------------
# 聚合读取：供 RAG 各环节一次性取全参数，避免多次查库
# ------------------------------------------------------------


class RuntimeConfig:
    """一次问答/一次入库流程内使用的配置快照。"""

    __slots__ = (
        "llm_base_url", "llm_api_key", "llm_model", "llm_aux_model",
        "rerank_api_url", "rerank_api_key", "rerank_top_k", "rerank_model",
        "rerank_provider", "rerank_version", "rerank_local_path",
        "embedding_model", "embedding_base_url", "embedding_api_key",
        "embedding_provider", "embedding_version", "embedding_local_path",
        "chunk_size", "chunk_overlap", "retrieval_top_n", "history_rounds",
    )

    def __init__(self, db: Session) -> None:
        self.llm_base_url = get(db, LLM_BASE_URL).rstrip("/")
        self.llm_api_key = get_secret(db, LLM_API_KEY)
        self.llm_model = get(db, LLM_MODEL)
        # 未单独配置时回退到主模型，保证行为与之前一致
        self.llm_aux_model = get(db, LLM_AUX_MODEL) or self.llm_model

        self.rerank_api_url = get(db, RERANK_API_URL)
        self.rerank_api_key = get_secret(db, RERANK_API_KEY)
        self.rerank_top_k = max(1, get_int(db, RERANK_TOP_K, 5))
        self.rerank_model = get(db, RERANK_MODEL)
        self.rerank_provider = get(db, RERANK_PROVIDER)
        self.rerank_version = get(db, RERANK_VERSION)
        self.rerank_local_path = get(db, RERANK_LOCAL_PATH)

        self.embedding_model = get(db, EMBEDDING_MODEL)
        self.embedding_base_url = (get(db, EMBEDDING_BASE_URL) or self.llm_base_url).rstrip("/")
        self.embedding_api_key = get_secret(db, EMBEDDING_API_KEY) or self.llm_api_key
        self.embedding_provider = get(db, EMBEDDING_PROVIDER)
        self.embedding_version = get(db, EMBEDDING_VERSION)
        self.embedding_local_path = get(db, EMBEDDING_LOCAL_PATH)

        self.chunk_size = max(100, get_int(db, CHUNK_SIZE, 600))
        self.chunk_overlap = max(0, min(get_int(db, CHUNK_OVERLAP, 60), self.chunk_size - 1))
        self.retrieval_top_n = max(1, get_int(db, RETRIEVAL_TOP_N, 20))
        self.history_rounds = max(0, get_int(db, HISTORY_ROUNDS, 5))


def load_runtime_config(db: Session) -> RuntimeConfig:
    return RuntimeConfig(db)
