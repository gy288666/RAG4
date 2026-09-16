"""文档处理服务：落盘 → 解析 → 切片 → 向量化入库 → 状态流转。

状态机（PRD 4.2.4）：``pending → parsing → vectorizing → ready / failed``
上传接口立即返回 ``pending``，实际处理在后台线程池中异步完成，
前端通过 ``GET /api/v1/docs/list`` 轮询状态与 ``updated_at`` 判断进度 [M-1]。
"""

from __future__ import annotations

import logging
import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import settings
from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.adapter import adapt_parse_result
from app.core.database import session_scope
from app.models.document import (
    STATUS_FAILED,
    STATUS_PARSING,
    STATUS_PENDING,
    STATUS_READY,
    STATUS_VECTORIZING,
    Document,
)
from app.models.usage_log import EVENT_OCR_CALL
from app.services import chunking_service, config_service, embedding_service, usage_service
from app.services import parser_service
from app.services.vector_store import VectorRecord, get_vector_store
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

#: 测试模式下同步执行，便于断言最终状态
SYNCHRONOUS_PROCESSING = False


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.WORKER_THREADS, thread_name_prefix="doc-worker"
            )
        return _executor


def shutdown_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


# ------------------------------------------------------------
# 上传
# ------------------------------------------------------------


def user_upload_dir(user_id: int) -> str:
    """按 user_id 分层的物理存储目录（PRD 4.2.1）。"""
    path = os.path.join(settings.UPLOAD_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def new_document_id() -> str:
    return generate_id("doc")


def save_uploaded_file(user_id: int, doc_id: str, file_name: str, content: bytes) -> str:
    """保存原始文件，返回物理路径。文件名使用 doc_id 避免路径穿越与重名覆盖。"""
    ext = os.path.splitext(file_name)[1].lower()
    path = os.path.join(user_upload_dir(user_id), f"{doc_id}{ext}")
    with open(path, "wb") as fp:
        fp.write(content)
    return path


def create_document(
    db: Session, *, user_id: int, doc_id: str, file_name: str, file_size: int, local_path: str
) -> Document:
    document = Document(
        id=doc_id,
        user_id=user_id,
        file_name=file_name,
        file_size=file_size,
        local_path=local_path,
        status=STATUS_PENDING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def enqueue(doc_id: str) -> None:
    """提交后台解析任务。"""
    if SYNCHRONOUS_PROCESSING:
        process_document(doc_id)
        return
    _get_executor().submit(_safe_process, doc_id)


def _safe_process(doc_id: str) -> None:
    try:
        process_document(doc_id)
    except Exception:  # pragma: no cover - 兜底，异常已在内部落库
        logger.exception("后台处理文档失败: %s", doc_id)


# ------------------------------------------------------------
# 核心处理流程
# ------------------------------------------------------------


def _update_status(doc_id: str, status: str) -> None:
    with session_scope() as db:
        document = db.get(Document, doc_id)
        if document is not None:
            document.status = status


def process_document(doc_id: str) -> str:
    """解析并向量化单个文档，返回最终状态。"""
    with session_scope() as db:
        document = db.get(Document, doc_id)
        if document is None:
            logger.warning("待处理文档不存在: %s", doc_id)
            return STATUS_FAILED
        # Rebuilds require Phase 2's staged index jobs; config toggles affect uploads.
        if document.status == STATUS_READY:
            logger.info("跳过已就绪文档（重建需版本化索引任务）: %s", doc_id)
            return STATUS_READY
        user_id = document.user_id
        file_name = document.file_name
        local_path = document.local_path
        config = config_service.load_runtime_config(db)

    try:
        # ---------- 1. 解析（含扫描版 PDF 的 OCR） ----------
        _update_status(doc_id, STATUS_PARSING)
        engine_name = settings.DOCUMENT_CHUNKING_ENGINE
        if engine_name not in {"rag3", "rag4"}:
            raise ValueError(f"未知切分器: {engine_name}")
        result = (
            parser_service.parse(local_path, file_name, structured=True)
            if engine_name == "rag4" else parser_service.parse(local_path, file_name)
        )

        if result.used_ocr:
            usage_service.record(
                event_type=EVENT_OCR_CALL,
                user_id=user_id,
                ref_id=doc_id,
                is_success=True,
            )

        # ---------- 2. 切片 ----------
        chunk_set = None
        with usage_service.track("document_chunking", user_id=user_id, ref_id=doc_id):
            if engine_name == "rag4":
                chunk_set = ChunkingEngine().split(
                    adapt_parse_result(result, document_id=doc_id, file_name=file_name),
                    ChunkingConfig(
                        chunking_version=settings.RAG4_CHUNKING_VERSION,
                        child_max_tokens=settings.RAG4_CHILD_MAX_TOKENS,
                        parent_max_tokens=settings.RAG4_PARENT_MAX_TOKENS,
                    ),
                )
                if not chunk_set.verify():
                    raise ValueError("ChunkSet identity/structure validation failed")
                chunks = chunk_set.child_chunks
            else:
                chunks = chunking_service.split_blocks(
                    result.blocks, chunk_size=config.chunk_size, overlap=config.chunk_overlap
                )
        if not chunks:
            raise parser_service.ParseError("文档内容为空，未生成任何有效文本切片")

        # ---------- 3. 向量化并写入用户专属 Collection ----------
        _update_status(doc_id, STATUS_VECTORIZING)
        embeddings = embedding_service.embed_texts(
            [c.text for c in chunks], config, user_id=user_id
        )

        if len(embeddings) != len(chunks):
            raise embedding_service.EmbeddingError("Embedding 数量与切片数量不一致，拒绝写入索引")

        records = [
            VectorRecord(
                id=chunk.chunk_id if chunk_set is not None else f"{doc_id}:{chunk.chunk_index}",
                text=chunk.text,
                embedding=embedding,
                # [S-3] Metadata 五要素，缺一不可
                doc_id=doc_id,
                user_id=user_id,
                file_name=file_name,
                chunk_index=chunk.chunk_index,
                page=chunk.page_start if chunk_set is not None else chunk.page,
                embedding_model_version=config.embedding_version,
                chunking_version=chunk_set.chunking_version if chunk_set else None,
                chunk_set_id=chunk_set.chunk_set_id if chunk_set else None,
                chunk_metadata_json=json.dumps(
                    {
                        **chunk.model_dump(mode="json", exclude={"text"}),
                        "parser_version": chunk_set.parser_version,
                        "tokenizer_id": chunk_set.tokenizer_id,
                        "engine_version": chunk_set.engine_version,
                    }, ensure_ascii=False, sort_keys=True,
                ) if chunk_set is not None else None,
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        get_vector_store().add(
            user_id,
            records,
            index_version=config.embedding_version,
        )

        _update_status(doc_id, STATUS_READY)
        logger.info(
            "文档处理完成: %s（%d 个切片，Embedding=%s，chunking=%s，chunk_set=%s）",
            doc_id,
            len(records),
            config.embedding_version,
            chunk_set.chunking_version if chunk_set else "rag3-baseline",
            chunk_set.chunk_set_id if chunk_set else None,
        )
        return STATUS_READY

    except parser_service.ParseError as exc:
        _handle_failure(doc_id, user_id, str(exc), ocr_related="OCR" in str(exc))
        return STATUS_FAILED
    except embedding_service.EmbeddingError as exc:
        _handle_failure(doc_id, user_id, str(exc))
        return STATUS_FAILED
    except Exception as exc:  # pragma: no cover
        logger.exception("文档处理异常: %s", doc_id)
        _handle_failure(doc_id, user_id, f"处理异常：{exc}")
        return STATUS_FAILED


def _handle_failure(doc_id: str, user_id: int, message: str, *, ocr_related: bool = False) -> None:
    logger.warning("文档处理失败 %s: %s", doc_id, message)
    _update_status(doc_id, STATUS_FAILED)
    usage_service.record(
        event_type=EVENT_OCR_CALL if ocr_related else "document_process",
        user_id=user_id,
        ref_id=doc_id,
        is_success=False,
        error_message=message,
    )


# ------------------------------------------------------------
# 删除
# ------------------------------------------------------------


def delete_document(db: Session, document: Document) -> None:
    """同步清理向量、物理文件与 MySQL 元数据（PRD 4.2.4）。"""
    user_id = document.user_id
    doc_id = document.id
    local_path = document.local_path

    try:
        # [S-3] 依据 metadata 中的 doc_id 一次性删除全部向量片段
        get_vector_store().delete_document(user_id, doc_id)
    except Exception:
        logger.warning("清理向量失败: doc_id=%s", doc_id, exc_info=True)

    try:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
    except OSError:
        logger.warning("删除物理文件失败: %s", local_path, exc_info=True)

    db.delete(document)
    db.commit()


def purge_user_storage(user_id: int) -> None:
    """删除用户时清理其全部物理文件与向量 Collection。"""
    try:
        get_vector_store().drop_user(user_id)
    except Exception:  # pragma: no cover
        logger.warning("删除用户 Collection 失败: %s", user_id, exc_info=True)
    path = os.path.join(settings.UPLOAD_DIR, str(user_id))
    shutil.rmtree(path, ignore_errors=True)
