from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=128, description="注册邮箱")
    password: str = Field(..., max_length=128, description="登录密码，不少于 6 位")


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=128)
    password: str = Field(..., max_length=128)


class ResetRequestPayload(BaseModel):
    email: str = Field(..., max_length=128)


class ChangePasswordRequest(BaseModel):
    """用户自行修改密码；成功后 token_version +1，旧 Token 立即失效 [S-2]。"""

    old_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


class UserInfo(BaseModel):
    id: int
    email: str
    role: str
