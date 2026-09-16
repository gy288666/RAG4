"""向量库抽象层（PRD 4.2.1 物理隔离 / 5.3 可扩展性）。

- ``BaseVectorStore`` 定义统一接口，未来迁移 Milvus / Qdrant 只需新增实现类。
- ``ChromaVectorStore`` 为默认实现：**每个用户一个独立 Collection**
  （``col_user_{user_id}``），从物理层面杜绝跨用户数据泄露。
- ``LocalVectorStore`` 为轻量兜底实现（纯 Python + JSON 持久化），
  在未安装 chromadb 的环境中保证功能完整可用。

[S-3] 每条向量的 Metadata 强制包含：doc_id / user_id / file_name / page / chunk_index，
否则删除文档时无法定位向量，会导致向量库残留垃圾数据。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


BASELINE_INDEX_VERSION = "baseline"


def collection_name(user_id: int, index_version: str = BASELINE_INDEX_VERSION) -> str:
    """用户与 Embedding 版本共同确定 Collection。

    ``baseline`` 保留 RAG3 的旧名称，已有索引无需迁移；新模型版本进入独立
    Collection，防止不同维度或语义空间的向量混写。
    """
    base = f"col_user_{user_id}"
    version = (index_version or BASELINE_INDEX_VERSION).strip()
    if version in {BASELINE_INDEX_VERSION, "legacy"}:
        return base
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", version).strip("_-").lower() or "index"
    digest = hashlib.sha256(version.encode("utf-8")).hexdigest()[:8]
    return f"{base}__{slug[:32]}_{digest}"


@dataclass(slots=True)
class VectorRecord:
    """待写入向量库的一条切片。"""

    id: str
    text: str
    embedding: list[float]
    doc_id: str
    user_id: int
    file_name: str
    chunk_index: int
    page: int | None = None
    embedding_model_version: str | None = None
    chunking_version: str | None = None
    chunk_set_id: str | None = None
    # Chroma metadata only accepts scalar values.
    chunk_metadata_json: str | None = None

    def metadata(self) -> dict[str, Any]:
        # 向量库通常不接受 None 值，page 为空时省略该键，读取侧统一用 .get()
        meta: dict[str, Any] = {
            "doc_id": self.doc_id,
            "user_id": int(self.user_id),
            "file_name": self.file_name,
            "chunk_index": int(self.chunk_index),
        }
        if self.page is not None:
            meta["page"] = int(self.page)
        if self.embedding_model_version:
            meta["embedding_model_version"] = self.embedding_model_version
        for key in ("chunking_version", "chunk_set_id", "chunk_metadata_json"):
            value = getattr(self, key)
            if value is not None:
                meta[key] = value
        return meta


def _retrieved_extra(meta: dict[str, Any]) -> dict[str, Any]:
    extra = {"embedding_model_version": meta.get("embedding_model_version")}
    if meta.get("chunking_version"):
        extra["chunking_version"] = meta["chunking_version"]
        extra["chunk_set_id"] = meta.get("chunk_set_id")
        if meta.get("chunk_metadata_json"):
            extra["chunking"] = json.loads(meta["chunk_metadata_json"])
    return extra


@dataclass(slots=True)
class RetrievedChunk:
    """检索命中的片段。"""

    text: str
    doc_id: str
    file_name: str
    chunk_index: int
    page: int | None = None
    score: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore:
    """向量库统一接口。"""

    def add(
        self,
        user_id: int,
        records: list[VectorRecord],
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> None:
        raise NotImplementedError

    def search(
        self,
        user_id: int,
        embedding: list[float],
        top_n: int,
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError

    def delete_document(
        self, user_id: int, doc_id: str, *, index_version: str | None = None
    ) -> None:
        raise NotImplementedError

    def drop_user(self, user_id: int) -> None:
        raise NotImplementedError

    def count(self, user_id: int, *, index_version: str = BASELINE_INDEX_VERSION) -> int:
        raise NotImplementedError


# ============================================================
# Chroma 实现
# ============================================================


class ChromaVectorStore(BaseVectorStore):
    def __init__(self, persist_dir: str) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._lock = threading.RLock()

    def _collection(self, user_id: int, index_version: str = BASELINE_INDEX_VERSION):
        with self._lock:
            return self._client.get_or_create_collection(
                name=collection_name(user_id, index_version),
                metadata={"hnsw:space": "cosine", "index_version": index_version},
            )

    def add(
        self,
        user_id: int,
        records: list[VectorRecord],
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> None:
        if not records:
            return
        collection = self._collection(user_id, index_version)
        collection.upsert(
            ids=[r.id for r in records],
            embeddings=[r.embedding for r in records],
            documents=[r.text for r in records],
            metadatas=[r.metadata() for r in records],
        )

    def search(
        self,
        user_id: int,
        embedding: list[float],
        top_n: int,
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> list[RetrievedChunk]:
        collection = self._collection(user_id, index_version)
        if collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_n, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for text, meta, distance in zip(documents, metadatas, distances):
            meta = meta or {}
            chunks.append(
                RetrievedChunk(
                    text=text or "",
                    doc_id=str(meta.get("doc_id", "")),
                    file_name=str(meta.get("file_name", "")),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    page=int(meta["page"]) if meta.get("page") is not None else None,
                    # cosine distance → 相似度
                    score=float(1.0 - float(distance)) if distance is not None else 0.0,
                    extra=_retrieved_extra(meta),
                )
            )
        return chunks

    def delete_document(
        self, user_id: int, doc_id: str, *, index_version: str | None = None
    ) -> None:
        # [S-3] 依赖 metadata 中的 doc_id 一次性清除该文档全部向量片段
        for name in self._user_collection_names(user_id, index_version):
            self._client.get_collection(name).delete(where={"doc_id": doc_id})

    def drop_user(self, user_id: int) -> None:
        with self._lock:
            for name in self._user_collection_names(user_id, None):
                try:
                    self._client.delete_collection(name)
                except Exception:  # 集合不存在时忽略
                    logger.debug("删除 Collection 失败（可能不存在）: %s", name)

    def count(self, user_id: int, *, index_version: str = BASELINE_INDEX_VERSION) -> int:
        return int(self._collection(user_id, index_version).count())

    def _user_collection_names(self, user_id: int, index_version: str | None) -> list[str]:
        if index_version is not None:
            name = collection_name(user_id, index_version)
            try:
                self._client.get_collection(name)
            except Exception:
                return []
            return [name]
        prefix = f"col_user_{user_id}"
        result: list[str] = []
        for collection in self._client.list_collections():
            name = collection if isinstance(collection, str) else collection.name
            if name == prefix or name.startswith(f"{prefix}__"):
                result.append(name)
        return result


# ============================================================
# 本地轻量实现（无 chromadb 依赖时的兜底）
# ============================================================


class LocalVectorStore(BaseVectorStore):
    """纯 Python 余弦相似度检索 + JSON 持久化。

    仅适用于小规模数据与开发环境；接口与 Chroma 实现完全一致，
    因此上层业务代码无需任何改动即可切换。
    """

    def __init__(self, persist_dir: str) -> None:
        self._dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, user_id: int, index_version: str = BASELINE_INDEX_VERSION) -> str:
        return os.path.join(self._dir, f"{collection_name(user_id, index_version)}.json")

    def _load(
        self, user_id: int, index_version: str = BASELINE_INDEX_VERSION
    ) -> list[dict[str, Any]]:
        path = self._path(user_id, index_version)
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as fp:
                return json.load(fp)
        except (OSError, json.JSONDecodeError):  # pragma: no cover
            return []

    def _save(
        self,
        user_id: int,
        rows: list[dict[str, Any]],
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> None:
        tmp = self._path(user_id, index_version) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(rows, fp, ensure_ascii=False)
        os.replace(tmp, self._path(user_id, index_version))

    def add(
        self,
        user_id: int,
        records: list[VectorRecord],
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> None:
        if not records:
            return
        with self._lock:
            rows = self._load(user_id, index_version)
            new_ids = {r.id for r in records}
            rows = [row for row in rows if row["id"] not in new_ids]
            rows.extend(asdict(r) for r in records)
            self._save(user_id, rows, index_version)

    def search(
        self,
        user_id: int,
        embedding: list[float],
        top_n: int,
        *,
        index_version: str = BASELINE_INDEX_VERSION,
    ) -> list[RetrievedChunk]:
        rows = self._load(user_id, index_version)
        if not rows:
            return []
        query_norm = math.sqrt(sum(v * v for v in embedding)) or 1.0
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            vector = row.get("embedding") or []
            if len(vector) != len(embedding):
                continue
            dot = sum(a * b for a, b in zip(embedding, vector))
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            scored.append((dot / (query_norm * norm), row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                text=row.get("text", ""),
                doc_id=row.get("doc_id", ""),
                file_name=row.get("file_name", ""),
                chunk_index=int(row.get("chunk_index", 0)),
                page=row.get("page"),
                score=float(score),
                extra=_retrieved_extra(row),
            )
            for score, row in scored[:top_n]
        ]

    def delete_document(
        self, user_id: int, doc_id: str, *, index_version: str | None = None
    ) -> None:
        with self._lock:
            paths = (
                [self._path(user_id, index_version)]
                if index_version is not None
                else self._user_paths(user_id)
            )
            for path in paths:
                if not os.path.exists(path):
                    continue
                rows = self._load_path(path)
                rows = [row for row in rows if row.get("doc_id") != doc_id]
                self._save_path(path, rows)

    def drop_user(self, user_id: int) -> None:
        with self._lock:
            for path in self._user_paths(user_id):
                if os.path.exists(path):
                    os.remove(path)

    def count(self, user_id: int, *, index_version: str = BASELINE_INDEX_VERSION) -> int:
        return len(self._load(user_id, index_version))

    def _user_paths(self, user_id: int) -> list[str]:
        prefix = f"col_user_{user_id}"
        return [
            os.path.join(self._dir, filename)
            for filename in os.listdir(self._dir)
            if filename == f"{prefix}.json"
            or (filename.startswith(f"{prefix}__") and filename.endswith(".json"))
        ]

    @staticmethod
    def _load_path(path: str) -> list[dict[str, Any]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as fp:
                return json.load(fp)
        except (OSError, json.JSONDecodeError):
            return []

    @staticmethod
    def _save_path(path: str, rows: list[dict[str, Any]]) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(rows, fp, ensure_ascii=False)
        os.replace(tmp, path)


# ============================================================
# 单例工厂
# ============================================================

_store: BaseVectorStore | None = None
_store_lock = threading.Lock()


def get_vector_store() -> BaseVectorStore:
    global _store
    with _store_lock:
        if _store is not None:
            return _store
        try:
            _store = ChromaVectorStore(settings.CHROMA_DIR)
            logger.info("向量库后端：Chroma (%s)", settings.CHROMA_DIR)
        except Exception as exc:
            logger.warning("Chroma 不可用（%s），回退到本地轻量向量库实现", exc)
            _store = LocalVectorStore(settings.CHROMA_DIR)
        return _store


def reset_vector_store() -> None:
    """测试辅助：重置单例。"""
    global _store
    with _store_lock:
        _store = None
