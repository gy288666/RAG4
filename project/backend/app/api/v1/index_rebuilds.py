"""Owner-scoped rebuild management. Creating a task does not schedule execution."""
import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.chunking import ChunkingConfig
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import APIException, BadRequest, NotFound, success
from app.models.user import User
from app.services import config_service, index_rebuild_service as rebuilds, usage_service
from app.services.embedding_service import build_endpoint
from app.services.index_build_service import EmbeddingSpec
from app.utils.datetime_utils import fmt

router = APIRouter(prefix="/index-rebuilds", tags=["索引重建"])


class CreateRebuildRequest(BaseModel):
    """Dimension must match the configured model; execution validates its output."""
    model_config = ConfigDict(extra="forbid")
    dimension: int = Field(strict=True, gt=0, le=65536)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$",
        description="可选、区分大小写的创建请求键；同键同参返回原任务，异参返回409，不刷新文档快照")


def serialize(task):
    request = json.loads(task.request_json)
    return {"id": task.id, "status": task.status, "base_revision": task.base_revision,
            "attempt": task.attempt, "cancel_requested": task.cancel_requested,
            "version_id": task.version_id, "error_code": task.error_code,
            "error_document_id": task.error_document_id, "duration_ms": task.duration_ms,
            "document_count": len(request["documents"]),
            "completed_document_count": len(json.loads(task.checkpoints_json)),
            "embedding_model": request["embedding"]["model_id"],
            "embedding_version": request["embedding"]["version"],
            "dimension": request["embedding"]["dimension"],
            "chunking_version": request["chunking"]["chunking_version"],
            "created_at": fmt(task.created_at), "finished_at": fmt(task.finished_at)}


@router.post("", summary="创建待执行重建任务（不自动调度）")
def create(body: CreateRebuildRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    with usage_service.track("index_rebuild_create", user_id=user.id):
        config = config_service.load_runtime_config(db)
        if config.embedding_provider != "remote":
            raise BadRequest("当前重建仅支持管理员配置的远程 Embedding")
        try:
            spec = EmbeddingSpec(endpoint=build_endpoint(config.embedding_base_url, "/embeddings"),
                                 model_id=config.embedding_model, version=config.embedding_version,
                                 dimension=body.dimension)
            task = rebuilds.create_rebuild(user.id, spec, body.chunking, idempotency_key=body.idempotency_key)
        except rebuilds.RebuildRequestConflict as error:
            raise APIException(409, "请求键已用于不同参数，请使用新键创建任务") from error
        except rebuilds.RebuildQuotaExceeded as error:
            raise APIException(429, "未完成重建任务已达配额，请等待完成或取消待执行/失败任务",
                               {"limit": error.limit, "open_count": error.open_count}) from error
        except (ValueError, OSError) as error:
            raise BadRequest("无法创建重建任务，请检查模型配置及文档就绪状态") from error
        return success(serialize(task))


@router.get("", summary="分页查询自己的重建任务")
def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            user: User = Depends(get_current_user)):
    tasks, total = rebuilds.list_rebuilds(user.id, limit=limit, offset=offset)
    return success({"items": [serialize(task) for task in tasks], "total": total,
                    "limit": limit, "offset": offset})


@router.get("/{task_id}", summary="查询自己的重建进度")
def detail(task_id: str, user: User = Depends(get_current_user)):
    try:
        return success(serialize(rebuilds.get_rebuild(user.id, task_id)))
    except LookupError as error:
        raise NotFound("重建任务不存在") from error


@router.post("/{task_id}/cancel", summary="取消自己的重建任务")
def cancel(task_id: str, user: User = Depends(get_current_user)):
    with usage_service.track("index_rebuild_cancel", user_id=user.id):
        try:
            return success(serialize(rebuilds.cancel_rebuild(user.id, task_id)))
        except LookupError as error:
            raise NotFound("重建任务不存在") from error
