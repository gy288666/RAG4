"""用户与认证模块 ``/api/v1/auth``（api_document 第 2 章）。"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import BadRequest, Forbidden, success
from app.core.security import (
    create_access_token,
    hash_password,
    validate_email,
    validate_password,
    verify_password,
)
from app.models.reset_request import PasswordResetRequest
from app.models.user import ROLE_USER, STATUS_ENABLED, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetRequestPayload,
)
from app.utils.datetime_utils import fmt, now

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", summary="用户注册")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()

    ok, message = validate_email(email)
    if not ok:
        raise BadRequest(message)
    ok, message = validate_password(payload.password)
    if not ok:
        raise BadRequest(message)

    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise BadRequest("该邮箱已被注册，请直接登录")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=ROLE_USER,
        status=STATUS_ENABLED,
        token_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return success(
        {"email": user.email, "created_at": fmt(user.created_at)}, message="注册成功，请登录"
    )


@router.post("/login", summary="用户登录")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # PRD 4.1.1：登录失败需给出明确提示
    if user is None:
        raise BadRequest("邮箱未注册")
    if not verify_password(payload.password, user.password_hash):
        raise BadRequest("密码错误")
    if user.status != STATUS_ENABLED:
        raise Forbidden("账号已被禁用，请联系管理员")

    token, expires_in = create_access_token(user.id, user.email, user.role, user.token_version)

    user.last_login_at = now()
    db.add(user)
    db.commit()

    return success(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "user_info": {"id": user.id, "email": user.email, "role": user.role},
        },
        message="登录成功",
    )


@router.post("/reset-request", summary="提交密码重置申请")
def reset_request(payload: ResetRequestPayload, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    ok, message = validate_email(email)
    if not ok:
        raise BadRequest(message)

    # [M-4] 同一邮箱 10 分钟内只允许提交 1 次；已有未处理申请直接拒绝
    threshold = now() - timedelta(minutes=settings.RESET_REQUEST_INTERVAL_MINUTES)
    pending = db.execute(
        select(PasswordResetRequest)
        .where(
            PasswordResetRequest.email == email,
            PasswordResetRequest.is_handled == 0,
            PasswordResetRequest.last_request_at > threshold,
        )
        .limit(1)
    ).scalar_one_or_none()
    if pending is not None:
        raise BadRequest(
            f"您已有待处理的申请，请联系管理员或 {settings.RESET_REQUEST_INTERVAL_MINUTES} 分钟后重试"
        )

    existing = db.execute(
        select(PasswordResetRequest)
        .where(PasswordResetRequest.email == email, PasswordResetRequest.is_handled == 0)
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        # 超过频率窗口的旧申请：刷新提交时间，避免同邮箱堆积多条待处理记录
        existing.last_request_at = now()
        db.add(existing)
    else:
        db.add(PasswordResetRequest(email=email, is_handled=0, last_request_at=now()))
    db.commit()

    # 出于安全考虑，邮箱是否已注册不在响应中体现
    return success(None, message="已提交重置申请，请联系管理员为您重置密码")


@router.get("/me", summary="获取当前登录用户信息")
def me(user: User = Depends(get_current_user)):
    return success(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "last_login_at": fmt(user.last_login_at),
            "created_at": fmt(user.created_at),
        },
        message="获取成功",
    )


@router.post("/change-password", summary="修改本人密码")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """PRD 4.1.2：修改成功后 token_version +1，此前颁发的所有 JWT 立即失效 [S-2]。"""
    if not verify_password(payload.old_password, user.password_hash):
        raise BadRequest("原密码不正确")
    ok, message = validate_password(payload.new_password)
    if not ok:
        raise BadRequest(message)
    if payload.old_password == payload.new_password:
        raise BadRequest("新密码不能与原密码相同")

    user.password_hash = hash_password(payload.new_password)
    user.token_version = int(user.token_version or 0) + 1
    db.add(user)

    # 将该邮箱的待处理重置申请标记为已完成
    requests = (
        db.execute(
            select(PasswordResetRequest).where(
                PasswordResetRequest.email == user.email, PasswordResetRequest.is_handled == 0
            )
        )
        .scalars()
        .all()
    )
    for item in requests:
        item.is_handled = 1
        item.handled_at = now()
        db.add(item)
    db.commit()

    # 立即下发新 Token，避免用户被自己的改密操作强制登出
    token, expires_in = create_access_token(user.id, user.email, user.role, user.token_version)
    return success(
        {"access_token": token, "token_type": "Bearer", "expires_in": expires_in},
        message="密码修改成功，其他设备需重新登录",
    )
