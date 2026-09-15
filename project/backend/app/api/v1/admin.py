"""管理员后台模块 ``/api/v1/admin``（api_document 第 5 章）。

所有接口均要求 Token 对应用户角色为 ``admin``（``get_current_admin`` 依赖）。
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.core.response import BadRequest, NotFound, success
from app.models.document import Document
from app.models.reset_request import PasswordResetRequest
from app.models.usage_log import (
    EVENT_LLM_CALL,
    EVENT_OCR_CALL,
    EVENT_RERANK_CALL,
    EVENT_VECTOR_SEARCH,
    UsageLog,
)
from app.models.user import ROLE_ADMIN, ROLE_USER, User
from app.schemas.admin import ConfigUpdateRequest, RoleStatusUpdate
from app.services import config_service
from app.services.security_helpers import generate_and_apply_temp_password
from app.utils.datetime_utils import fmt, now

router = APIRouter(prefix="/admin", tags=["管理后台"])


# ============================================================
# 5.1 用户列表
# ============================================================


@router.get("/users", summary="获取所有用户列表")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, description="按邮箱模糊搜索"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    conditions = []
    if keyword and keyword.strip():
        conditions.append(User.email.like(f"%{keyword.strip()}%"))

    total = db.execute(select(func.count(User.id)).where(*conditions)).scalar_one()
    users = (
        db.execute(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    doc_counts: dict[int, int] = {}
    if users:
        rows = db.execute(
            select(Document.user_id, func.count(Document.id))
            .where(Document.user_id.in_([u.id for u in users]))
            .group_by(Document.user_id)
        ).all()
        doc_counts = {user_id: count for user_id, count in rows}

    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "user_id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "status": u.status,
                    "doc_count": doc_counts.get(u.id, 0),
                    "last_login_at": fmt(u.last_login_at),
                    "created_at": fmt(u.created_at),
                }
                for u in users
            ],
        },
        message="获取成功",
    )


# ============================================================
# 5.2 变更角色与状态
# ============================================================


@router.put("/users/{user_id}/role-status", summary="变更用户角色与状态")
def update_role_status(
    user_id: int,
    payload: RoleStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if payload.role is None and payload.status is None:
        raise BadRequest("请至少提供 role 或 status 其中一个字段")

    user = db.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")

    if payload.role is not None:
        if payload.role not in (ROLE_USER, ROLE_ADMIN):
            raise BadRequest('role 仅支持 "user" 或 "admin"')
        if user.id == admin.id and payload.role != ROLE_ADMIN:
            raise BadRequest("不能取消自己的管理员角色")
        user.role = payload.role

    if payload.status is not None:
        if payload.status not in (0, 1):
            raise BadRequest("status 仅支持 1（启用）或 0（禁用）")
        if user.id == admin.id and payload.status == 0:
            raise BadRequest("不能禁用当前登录的管理员账号")
        user.status = payload.status

    db.add(user)
    db.commit()
    return success(None, message="更新用户角色和状态成功")


# ============================================================
# 5.3 / 5.4 密码重置
# ============================================================


@router.get("/reset-requests", summary="密码重置请求列表")
def list_reset_requests(
    include_handled: bool = Query(False, description="是否包含已处理记录"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    conditions = [] if include_handled else [PasswordResetRequest.is_handled == 0]
    rows = (
        db.execute(
            select(PasswordResetRequest)
            .where(*conditions)
            .order_by(PasswordResetRequest.last_request_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )

    # 关联用户 ID，便于管理员一键跳转到重置密码操作
    emails = [r.email for r in rows]
    user_map: dict[str, int] = {}
    if emails:
        user_rows = db.execute(select(User.email, User.id).where(User.email.in_(emails))).all()
        user_map = {email: user_id for email, user_id in user_rows}

    return success(
        [
            {
                "id": r.id,
                "email": r.email,
                "user_id": user_map.get(r.email),
                "is_handled": r.is_handled,
                "requested_at": fmt(r.requested_at),
                "last_request_at": fmt(r.last_request_at),
                "handled_at": fmt(r.handled_at),
            }
            for r in rows
        ],
        message="获取成功",
    )


@router.put("/users/{user_id}/reset-password", summary="管理员手动重置用户密码")
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")

    # 生成临时密码并使该用户此前所有 JWT 立即失效 [S-2]
    temporary_password = generate_and_apply_temp_password(db, user)
    return success({"temporary_password": temporary_password}, message="重置密码成功")


# ============================================================
# 5.5 / 5.6 系统配置
# ============================================================


@router.get("/configs", summary="获取系统全局配置参数")
def get_configs(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    """[S-1] API Key 一律以脱敏掩码返回，绝不返回明文。"""
    return success(
        {
            "llm": {
                "base_url": config_service.get(db, config_service.LLM_BASE_URL),
                "api_key_masked": config_service.masked(db, config_service.LLM_API_KEY),
                "model": config_service.get(db, config_service.LLM_MODEL),
                "aux_model": config_service.get(db, config_service.LLM_AUX_MODEL),
            },
            "rerank": {
                "provider": config_service.get(db, config_service.RERANK_PROVIDER),
                "api_url": config_service.get(db, config_service.RERANK_API_URL),
                "api_key_masked": config_service.masked(db, config_service.RERANK_API_KEY),
                "model": config_service.get(db, config_service.RERANK_MODEL),
                "version": config_service.get(db, config_service.RERANK_VERSION),
                "local_path": config_service.get(db, config_service.RERANK_LOCAL_PATH),
                "top_k": config_service.get_int(db, config_service.RERANK_TOP_K, 5),
            },
            "embedding": {
                "provider": config_service.get(db, config_service.EMBEDDING_PROVIDER),
                "model": config_service.get(db, config_service.EMBEDDING_MODEL),
                "version": config_service.get(db, config_service.EMBEDDING_VERSION),
                "local_path": config_service.get(db, config_service.EMBEDDING_LOCAL_PATH),
                "base_url": config_service.get(db, config_service.EMBEDDING_BASE_URL),
                "api_key_masked": config_service.masked(db, config_service.EMBEDDING_API_KEY),
            },
            "chunking": {
                "chunk_size": config_service.get_int(db, config_service.CHUNK_SIZE, 600),
                "overlap": config_service.get_int(db, config_service.CHUNK_OVERLAP, 60),
            },
            "retrieval": {
                "top_n": config_service.get_int(db, config_service.RETRIEVAL_TOP_N, 20),
                "history_rounds": config_service.get_int(db, config_service.HISTORY_ROUNDS, 5),
            },
        },
        message="获取配置成功",
    )


@router.put("/configs", summary="更新系统全局配置参数")
def update_configs(
    payload: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """所有字段均为可选；API Key 由后端 AES-256 加密后写入数据库 [S-1]。"""
    updates: list[tuple[str, str]] = []

    if payload.llm:
        if payload.llm.base_url is not None:
            updates.append((config_service.LLM_BASE_URL, payload.llm.base_url.strip()))
        if payload.llm.model is not None:
            updates.append((config_service.LLM_MODEL, payload.llm.model.strip()))
        if payload.llm.aux_model is not None:
            updates.append((config_service.LLM_AUX_MODEL, payload.llm.aux_model.strip()))
        # 空字符串视为「不修改」，避免前端回显掩码时误清空已有 Key
        if payload.llm.api_key:
            updates.append((config_service.LLM_API_KEY, payload.llm.api_key.strip()))

    if payload.rerank:
        if payload.rerank.provider is not None:
            updates.append((config_service.RERANK_PROVIDER, payload.rerank.provider))
        if payload.rerank.api_url is not None:
            updates.append((config_service.RERANK_API_URL, payload.rerank.api_url.strip()))
        if payload.rerank.model is not None:
            updates.append((config_service.RERANK_MODEL, payload.rerank.model.strip()))
        if payload.rerank.version is not None:
            updates.append((config_service.RERANK_VERSION, payload.rerank.version.strip()))
        if payload.rerank.local_path is not None:
            updates.append((config_service.RERANK_LOCAL_PATH, payload.rerank.local_path.strip()))
        if payload.rerank.top_k is not None:
            updates.append((config_service.RERANK_TOP_K, str(payload.rerank.top_k)))
        if payload.rerank.api_key:
            updates.append((config_service.RERANK_API_KEY, payload.rerank.api_key.strip()))

    if payload.embedding:
        current_embedding_identity = (
            config_service.get(db, config_service.EMBEDDING_PROVIDER),
            config_service.get(db, config_service.EMBEDDING_MODEL),
            config_service.get(db, config_service.EMBEDDING_LOCAL_PATH),
        )
        next_embedding_identity = (
            payload.embedding.provider or current_embedding_identity[0],
            payload.embedding.model.strip()
            if payload.embedding.model is not None
            else current_embedding_identity[1],
            payload.embedding.local_path.strip()
            if payload.embedding.local_path is not None
            else current_embedding_identity[2],
        )
        current_version = config_service.get(db, config_service.EMBEDDING_VERSION)
        next_version = payload.embedding.version or current_version
        if next_embedding_identity != current_embedding_identity and next_version == current_version:
            raise BadRequest("更换 Embedding Adapter 或模型时必须同时填写新的模型版本")

        if payload.embedding.provider is not None:
            updates.append((config_service.EMBEDDING_PROVIDER, payload.embedding.provider))
        if payload.embedding.model is not None:
            updates.append((config_service.EMBEDDING_MODEL, payload.embedding.model.strip()))
        if payload.embedding.version is not None:
            updates.append((config_service.EMBEDDING_VERSION, payload.embedding.version.strip()))
        if payload.embedding.local_path is not None:
            updates.append((config_service.EMBEDDING_LOCAL_PATH, payload.embedding.local_path.strip()))
        if payload.embedding.base_url is not None:
            updates.append((config_service.EMBEDDING_BASE_URL, payload.embedding.base_url.strip()))
        if payload.embedding.api_key:
            updates.append((config_service.EMBEDDING_API_KEY, payload.embedding.api_key.strip()))

    if payload.chunking:
        if payload.chunking.chunk_size is not None:
            updates.append((config_service.CHUNK_SIZE, str(payload.chunking.chunk_size)))
        if payload.chunking.overlap is not None:
            updates.append((config_service.CHUNK_OVERLAP, str(payload.chunking.overlap)))

    if payload.retrieval:
        if payload.retrieval.top_n is not None:
            updates.append((config_service.RETRIEVAL_TOP_N, str(payload.retrieval.top_n)))
        if payload.retrieval.history_rounds is not None:
            updates.append((config_service.HISTORY_ROUNDS, str(payload.retrieval.history_rounds)))

    if not updates:
        raise BadRequest("没有需要更新的配置项")

    # 重叠字符数必须小于切片大小，否则切片会陷入死循环式重复
    pending = dict(updates)
    chunk_size = int(
        pending.get(config_service.CHUNK_SIZE)
        or config_service.get_int(db, config_service.CHUNK_SIZE, 600)
    )
    overlap = int(
        pending.get(config_service.CHUNK_OVERLAP)
        or config_service.get_int(db, config_service.CHUNK_OVERLAP, 60)
    )
    if overlap >= chunk_size:
        raise BadRequest("重叠字符数（overlap）必须小于切片大小（chunk_size）")

    for key, value in updates:
        config_service.set_value(db, key, value, commit=False)
    db.commit()
    config_service.invalidate_cache()
    from app.modeling.registry import clear_model_cache

    clear_model_cache()

    return success(None, message="系统全局配置参数已成功保存并立即生效")


# ============================================================
# 5.7 运行监控
# ============================================================


@router.get("/stats", summary="运行监控数据")
def get_stats(
    days: int = Query(7, ge=1, le=365, description="统计最近 N 天"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    since = now() - timedelta(days=days)

    rows = db.execute(
        select(
            UsageLog.event_type,
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.tokens_used), 0),
            func.coalesce(func.sum(case((UsageLog.is_success == 0, 1), else_=0)), 0),
        )
        .where(UsageLog.created_at >= since)
        .group_by(UsageLog.event_type)
    ).all()

    counts = {event: int(count) for event, count, _, _ in rows}
    tokens = {event: int(total) for event, _, total, _ in rows}
    failures = {event: int(failed) for event, _, _, failed in rows}

    total_calls = sum(counts.values())
    failure_count = sum(failures.values())
    failure_rate = (failure_count / total_calls * 100) if total_calls else 0.0

    # OCR 失败队列：usage_logs 的失败记录通过 ref_id 关联到具体文档
    failed_logs = (
        db.execute(
            select(UsageLog)
            .where(
                UsageLog.created_at >= since,
                UsageLog.is_success == 0,
                UsageLog.event_type.in_([EVENT_OCR_CALL, "document_process"]),
            )
            .order_by(UsageLog.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    doc_ids = [log.ref_id for log in failed_logs if log.ref_id]
    doc_map: dict[str, Document] = {}
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        doc_map = {d.id: d for d in docs}

    ocr_failed_queue = [
        {
            "doc_id": log.ref_id,
            "file_name": doc_map[log.ref_id].file_name if log.ref_id in doc_map else "（已删除）",
            "error": log.error_message or "未知错误",
            "created_at": fmt(log.created_at),
        }
        for log in failed_logs
        if log.ref_id
    ]

    # 每日调用趋势，供后台图表展示
    daily_rows = db.execute(
        select(func.date(UsageLog.created_at), func.count(UsageLog.id))
        .where(UsageLog.created_at >= since)
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    ).all()

    return success(
        {
            "period_days": days,
            "total_calls": total_calls,
            "total_llm_calls": counts.get(EVENT_LLM_CALL, 0),
            "total_tokens_used": tokens.get(EVENT_LLM_CALL, 0),
            "total_rerank_calls": counts.get(EVENT_RERANK_CALL, 0),
            "total_ocr_calls": counts.get(EVENT_OCR_CALL, 0),
            "total_vector_searches": counts.get(EVENT_VECTOR_SEARCH, 0),
            "failure_count": failure_count,
            "failure_rate": f"{failure_rate:.2f}%",
            "daily_trend": [{"date": str(day), "count": int(count)} for day, count in daily_rows],
            "ocr_failed_queue": ocr_failed_queue,
        },
        message="获取成功",
    )
