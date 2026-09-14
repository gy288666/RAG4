"""FastAPI 应用入口。

启动：``uvicorn app.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.response import register_exception_handlers, success
from app.services import document_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_DIR, exist_ok=True)
    init_db()
    _bootstrap()
    logger.info("%s v%s 启动完成", settings.APP_NAME, settings.APP_VERSION)
    if settings.DEV_MOCK_AI:
        logger.warning("DEV_MOCK_AI 已开启：Embedding / LLM / Rerank 使用本地 Mock，严禁用于生产")
    yield
    document_service.shutdown_executor()


def _bootstrap() -> None:
    """补齐默认系统配置，并在库中无管理员时创建初始管理员账号。"""
    from sqlalchemy import select

    from app.core.database import session_scope
    from app.core.security import hash_password
    from app.models.user import ROLE_ADMIN, User
    from app.services import config_service

    with session_scope() as db:
        config_service._load_all(db)  # 首次启动写入默认配置项

        exists = db.execute(select(User).where(User.role == ROLE_ADMIN).limit(1)).scalar_one_or_none()
        if exists is None:
            email = os.getenv("INIT_ADMIN_EMAIL", "admin@outlook.com")
            password = os.getenv("INIT_ADMIN_PASSWORD", "please-change-me")
            db.add(
                User(
                    email=email.lower(),
                    password_hash=hash_password(password),
                    role=ROLE_ADMIN,
                    status=1,
                )
            )
            logger.warning("已创建初始管理员账号 %s，请登录后立即修改密码", email)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于 RAG 的学术知识引擎后端服务",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/api/health", tags=["系统"], summary="健康检查")
def health():
    return success(
        {"status": "ok", "version": settings.APP_VERSION, "mock_ai": settings.DEV_MOCK_AI},
        message="服务运行正常",
    )
