"""FastAPI 依赖注入：JWT 鉴权、角色校验。"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models.user import ROLE_ADMIN, STATUS_ENABLED, User


def _extract_token(request: Request) -> str:
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        raise Unauthorized("缺少访问令牌，请先登录")
    token = header[7:].strip()
    if not token:
        raise Unauthorized("缺少访问令牌，请先登录")
    return token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """解析 JWT 并返回当前用户。

    校验链：签名/过期 → 用户存在 → 账号启用 → token_version 未失效 [S-2]。
    """
    payload = decode_access_token(_extract_token(request))
    if not payload:
        raise Unauthorized("登录状态已失效或令牌无效，请重新登录")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise Unauthorized("令牌内容异常，请重新登录")

    user = db.get(User, user_id)
    if user is None:
        raise Unauthorized("账号不存在，请重新登录")
    if user.status != STATUS_ENABLED:
        raise Forbidden("账号已被禁用，请联系管理员")

    # [S-2] Token 携带的版本号小于数据库当前值 → 强制重新登录
    if int(payload.get("token_version", -1)) < int(user.token_version or 0):
        raise Unauthorized("密码已变更，请重新登录")

    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise Forbidden("权限不足，该操作仅限管理员")
    return user
