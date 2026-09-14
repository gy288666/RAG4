"""与用户账号安全相关的复合操作。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import generate_temporary_password, hash_password
from app.models.reset_request import PasswordResetRequest
from app.models.user import User
from app.utils.datetime_utils import now


def generate_and_apply_temp_password(db: Session, user: User) -> str:
    """为用户生成临时密码并落库。

    同步完成三件事（PRD 4.1.2 / [S-2]）：
    1. 写入新的 bcrypt 密码哈希；
    2. ``token_version + 1``，使该用户此前颁发的所有 JWT 立即失效；
    3. 将其待处理的密码重置申请标记为已完成。
    """
    temporary_password = generate_temporary_password()

    user.password_hash = hash_password(temporary_password)
    user.token_version = int(user.token_version or 0) + 1
    db.add(user)

    requests = (
        db.execute(
            select(PasswordResetRequest).where(
                PasswordResetRequest.email == user.email,
                PasswordResetRequest.is_handled == 0,
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
    return temporary_password
