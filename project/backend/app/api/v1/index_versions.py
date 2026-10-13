"""Explicit owner-scoped CAS activation, rollback and baseline deactivation."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import get_current_user
from app.core.response import APIException, BadRequest, NotFound, success
from app.models.user import User
from app.services import index_version_service as versions

router = APIRouter(prefix="/index-versions", tags=["索引版本"])


class SwitchVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Required even when null: omitting this field must never deactivate implicitly.
    version_id: str | None = Field(..., min_length=1, max_length=64)
    expected_revision: int = Field(strict=True, ge=0)


def state(version_id, revision):
    return {"version_id": version_id, "revision": revision}


@router.get("/active", summary="查看自己的 active 索引与 revision")
def active(user: User = Depends(get_current_user)):
    return success(state(*versions.active_state(user.id)))


@router.put("/active", summary="显式激活、回滚或停用自己的索引")
def switch(body: SwitchVersionRequest, user: User = Depends(get_current_user)):
    try:
        result = versions.switch_version(user.id, body.version_id, expected_revision=body.expected_revision)
        return success(state(*result))
    except versions.ActiveRevisionConflict as error:
        raise APIException(409, "索引版本已发生变化，请刷新状态后重新确认") from error
    except LookupError as error:
        raise NotFound("索引版本不存在") from error
    except ValueError as error:
        raise BadRequest("索引未通过完整性或文档一致性检查，请重建或停用") from error


@router.get("", summary="分页查看自己的历史索引版本（不验证可激活性）")
def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            user: User = Depends(get_current_user)):
    return success(versions.list_versions(user.id, limit=limit, offset=offset))


# Register after /active so the literal path can never be treated as a version ID.
@router.get("/{version_id}", summary="查看自己的历史版本摘要与文档清单")
def detail(version_id: str, user: User = Depends(get_current_user)):
    try:
        return success(versions.describe_version(user.id, version_id))
    except LookupError as error:
        raise NotFound("索引版本不存在") from error
