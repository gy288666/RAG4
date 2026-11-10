"""Opt-in owner-scoped research. Each run request executes one bounded tool."""
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from typing import Literal

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import APIException, BadRequest, NotFound, success
from app.models.user import User
from app.research.agent import TaskConflict
from app.research.model import CompletionSpec
from app.research.verification_context import VerificationContextPolicy
from app.research.result_conditions import ResultConditionPolicy
from app.research.runtime import configured_agent, create_task, prepare_task, task_preview, read_partial_artifact, read_retry, retry_failed, read_claim_review, record_claim_review
from app.research.store import SQLResearchTaskStore
from app.research.tasks import TaskBudget, PlanVersion, ContextPolicy, CandidatePolicy
from app.services import config_service
from app.services.embedding_service import build_endpoint

router = APIRouter(prefix="/research-tasks", tags=["文献研究"])


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_version_id: str = Field(min_length=1, max_length=64)
    document_ids: tuple[str, ...] = Field(min_length=3, max_length=5)
    goal: str = Field(min_length=1, max_length=2000)
    budget: TaskBudget | None = None
    plan_version: PlanVersion = "research-comparison-v1"
    context_policy: ContextPolicy = "parent-floor-v2"
    candidate_policy: CandidatePolicy = "vector-v1"
    extraction_protocol: Literal["literal-quote-v1", "source-handles-v2"] = "source-handles-v2"
    response_format: Literal["text", "json_object"] = "text"
    verification_protocol: Literal["numeric-model-v2", "source-checks-v3", "source-handles-v4", "facet-handles-v5"] = "numeric-model-v2"
    verification_context_policy: VerificationContextPolicy='cited-chunk-v1'
    result_condition_policy: ResultConditionPolicy='model-only-v1'


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern="^(pause|resume|cancel)$")
    expected_revision: int = Field(strict=True, ge=0)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(strict=True, ge=0)


class ClaimReviewRequest(RunRequest):
    source_artifact_id: str=Field(min_length=1,max_length=100)
    decision: Literal['retain','withdraw','reset']
    reason: str=Field(min_length=1,max_length=1000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Review reason required')
        return value


class ConfirmCreateRequest(CreateRequest):
    # Optional for historical CLI/API clients; the UI always confirms its preview.
    expected_preview_id: str | None = Field(default=None, pattern='^[0-9a-f]{64}$')


def _draft_arguments(body, config):
    return dict(budget=body.budget, plan_version=body.plan_version, context_policy=body.context_policy,
        candidate_policy=body.candidate_policy, completion=CompletionSpec(endpoint=build_endpoint(config.llm_base_url, 'chat/completions'),
            model_id=config.llm_model, extraction_protocol=body.extraction_protocol,
            response_format=body.response_format, verification_protocol=body.verification_protocol,
            verification_context_policy=body.verification_context_policy, result_condition_policy=body.result_condition_policy))


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
def create(body: ConfirmCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = config_service.load_runtime_config(db)
    return _handle(lambda: create_task(user.id, body.index_version_id, body.document_ids, body.goal,
        expected_preview_id=body.expected_preview_id, **_draft_arguments(body, config)).model_dump(mode="json"))


@router.post('/preview', summary='校验来源并预览固定计划（不创建任务或执行模型）')
def preview(body: CreateRequest, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    config = config_service.load_runtime_config(db)
    return _handle(lambda: task_preview(prepare_task(user.id, body.index_version_id, body.document_ids, body.goal,
        **_draft_arguments(body, config))))


@router.get("", summary="查询自己的研究任务")
def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user)):
    items, total = SQLResearchTaskStore().listing(user.id, limit=limit, offset=offset)
    return success({"items": items, "total": total, "limit": limit, "offset": offset})


@router.get("/{task_id}", summary="查看计划、步骤、证据引用与产物")
def detail(task_id: str, user: User = Depends(get_current_user)):
    return _handle(lambda: SQLResearchTaskStore().load(user.id, task_id).model_dump(mode="json"))


@router.get('/{task_id}/partial-artifact', summary='只读查看失败任务的部分比较稿与原文来源')
def partial_artifact(task_id: str, response: Response, expected_revision: int | None = Query(None,ge=0), user: User = Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return _handle(lambda: read_partial_artifact(user.id,task_id,expected_revision=expected_revision).model_dump(mode='json'))


@router.post("/{task_id}/run", summary="执行一个工具并保存进度")
def run(task_id: str, body: RunRequest | None = None, user: User = Depends(get_current_user)):
    return _handle(lambda: configured_agent().step(user.id, task_id,
        expected_revision=body.expected_revision if body is not None else None).model_dump(mode="json"))


@router.get('/{task_id}/review',summary='查看自己的完成产物及结论审阅覆盖视图')
def claim_review(task_id: str,response: Response,expected_revision: int|None=Query(None,ge=0),user: User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return _handle(lambda:read_claim_review(user.id,task_id,expected_revision=expected_revision).model_dump(mode='json'))


@router.post('/{task_id}/claims/{claim_id}/review',summary='记录自己的结论保留/撤下/重置，不改原机器稿')
def review_claim(task_id: str,claim_id: str,body: ClaimReviewRequest,response: Response,user: User=Depends(get_current_user)):
    response.headers['Cache-Control']='no-store'
    return _handle(lambda:record_claim_review(user.id,task_id,claim_id,**body.model_dump()).model_dump(mode='json'))


@router.post("/{task_id}/control", summary="暂停、恢复或取消自己的任务")
def control(task_id: str, body: ControlRequest, user: User = Depends(get_current_user)):
    # Controls must work even when vector storage or model configuration is down.
    from app.research.agent import ResearchAgent
    return _handle(lambda: ResearchAgent(SQLResearchTaskStore(), None).control(user.id, task_id,
        body.action, body.expected_revision).model_dump(mode="json"))


@router.get('/{task_id}/retry', summary='只读核对已结束网络失败的恢复准入')
def retry_info(task_id: str, response: Response, user: User = Depends(get_current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return _handle(lambda: read_retry(user.id, task_id).model_dump(mode='json'))


@router.post('/{task_id}/retry', summary='显式准备恢复：保留预算，仅改为待执行')
def retry(task_id: str, body: RunRequest, user: User = Depends(get_current_user)):
    return _handle(lambda: retry_failed(user.id, task_id, expected_revision=body.expected_revision).model_dump(mode='json'))
