"""安全工具：bcrypt 密码哈希、JWT 签发校验、AES-256 配置加密。

对应 PRD 5.2：
- 密码使用 bcrypt 单向哈希（拒绝明文存储）
- JWT 携带 token_version，支持主动失效 [S-2]
- system_configs 中的 API Key 静态加密（AES-256-GCM）[S-1]
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# ============================================================
# 密码哈希
# ============================================================

_BCRYPT_MAX_BYTES = 72  # bcrypt 算法本身的输入长度上限


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_temporary_password(length: int = 12) -> str:
    """管理员重置密码时生成的随机临时密码（api_document 5.4）。"""
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"Temp_{body}"


# ============================================================
# 邮箱与密码规则校验（PRD 4.1.1）
# ============================================================

# 主流邮箱后缀白名单
ALLOWED_EMAIL_DOMAINS: tuple[str, ...] = (
    "outlook.com",
    "hotmail.com",
    "qq.com",
    "gmail.com",
    "163.com",
    "126.com",
    "foxmail.com",
    "sina.com",
    "yeah.net",
    "edu.cn",
)

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

MIN_PASSWORD_LENGTH = 6


def validate_email(email: str) -> tuple[bool, str]:
    """校验邮箱格式与后缀白名单，返回 (是否通过, 错误提示)。"""
    email = (email or "").strip()
    if not email or not _EMAIL_RE.match(email):
        return False, "邮箱格式不符合规范"
    domain = email.rsplit("@", 1)[-1].lower()
    if not any(domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS):
        allowed = "、".join(f"@{d}" for d in ALLOWED_EMAIL_DOMAINS[:5])
        return False, f"暂仅支持主流邮箱注册（如 {allowed} 等）"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return False, f"密码长度不得少于 {MIN_PASSWORD_LENGTH} 位"
    return True, ""


# ============================================================
# JWT
# ============================================================


def create_access_token(user_id: int, email: str, role: str, token_version: int) -> tuple[str, int]:
    """签发 JWT，返回 (token, 有效期秒数)。"""
    expires_in = settings.JWT_EXPIRE_SECONDS
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        # [S-2] 颁发时的 token_version，鉴权时与数据库比对
        "token_version": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析并校验 JWT；失败（过期/签名错误）返回 None。"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ============================================================
# AES-256-GCM 对称加密（system_configs 中的 API Key）[S-1]
# ============================================================

_ENC_PREFIX = "enc::v1::"


def _aes_key() -> bytes:
    raw = settings.CONFIG_ENCRYPTION_KEY or settings.SECRET_KEY
    # SHA-256 派生出固定 32 字节（256 位）密钥
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """AES-256-GCM 加密，输出 ``enc::v1::<base64(nonce+ciphertext)>``。"""
    if plaintext is None or plaintext == "":
        return ""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _ENC_PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(stored: str) -> str:
    """解密密文；对未加密的历史明文值原样返回，保证平滑兼容。"""
    if not stored:
        return ""
    if not stored.startswith(_ENC_PREFIX):
        return stored
    try:
        blob = base64.b64decode(stored[len(_ENC_PREFIX) :])
        return AESGCM(_aes_key()).decrypt(blob[:12], blob[12:], None).decode("utf-8")
    except Exception:
        # 密钥轮换或数据损坏时不抛出，避免整个配置读取失败
        return ""


def mask_secret(plaintext: str) -> str:
    """脱敏掩码，如 ``sk-****Flash``；任何响应都不得返回明文 [S-1]。"""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:3]}****{plaintext[-4:]}"
