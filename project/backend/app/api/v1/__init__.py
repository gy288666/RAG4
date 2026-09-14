"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, docs

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(docs.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
