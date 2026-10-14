"""Opt-in owner-scoped research. Each run request executes one bounded tool."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from typing import Literal

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import APIException, BadRequest, NotFound, success
from app.models.user import User
from app.research.agent import TaskConflict
from app.research.model import CompletionSpec
from app.research.runtime import configured_agent, create_task
from app.research.store import SQLResearchTaskStore
from app.research.tasks import TaskBudget
from app.services import config_service
from app.services.embedding_service import build_endpoint

router = APIRouter(prefix="/research-tasks", tags=["文献研究"])


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_version_id: str = Field(min_length=1, max_length=64)
    document_ids: tuple[str, ...] = Field(min_length=3, max_length=5)
    goal: str = Field(min_length=1, max_length=2000)
    budget: TaskBudget = Field(default_factory=TaskBudget)
    extraction_protocol: Literal["literal-quote-v1", "source-handles-v2"] = "source-handles-v2"
    response_format: Literal["text", "json_object"] = "text"


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern="^(pause|resume|cancel)$")
    expected_revision: int = Field(strict=True, ge=0)


def _handle(action):
    try:
        return success(action())
    except LookupError as error:
        raise NotFound("研究任务或来源不存在") from error
    except TaskConflict as error:
        raise APIException(409, "研究任务状态已变化，请重新读取后操作") from error
    except (ValueError, OSError) as error:
        raise BadRequest("研究来源、快照、模型配置或预算不满足要求") from error


@router.post("", summary="创建文献比较任务（不自动执行）")
def create(body: CreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = config_service.load_runtime_config(db)
    return _handle(lambda: create_task(user.id, body.index_version_id, body.document_ids, body.goal,
        budget=body.budget, completion=CompletionSpec(endpoint=build_endpoint(config.llm_base_url, "chat/completions"),
            model_id=config.llm_model, extraction_protocol=body.extraction_protocol,
            response_format=body.response_format)).model_dump(mode="json"))


@router.get("", summary="查询自己的研究任务")
def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user)):
    items, total = SQLResearchTaskStore().listing(user.id, limit=limit, offset=offset)
    return success({"items": items, "total": total, "limit": limit, "offset": offset})


@router.get("/{task_id}", summary="查看计划、步骤、证据引用与产物")
def detail(task_id: str, user: User = Depends(get_current_user)):
    return _handle(lambda: SQLResearchTaskStore().load(user.id, task_id).model_dump(mode="json"))


@router.post("/{task_id}/run", summary="执行一个工具并保存进度")
def run(task_id: str, user: User = Depends(get_current_user)):
    return _handle(lambda: configured_agent().step(user.id, task_id).model_dump(mode="json"))


@router.post("/{task_id}/control", summary="暂停、恢复或取消自己的任务")
def control(task_id: str, body: ControlRequest, user: User = Depends(get_current_user)):
    # Controls must work even when vector storage or model configuration is down.
    from app.research.agent import ResearchAgent
    return _handle(lambda: ResearchAgent(SQLResearchTaskStore(), None).control(user.id, task_id,
        body.action, body.expected_revision).model_dump(mode="json"))
