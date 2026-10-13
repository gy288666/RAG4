"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, docs, index_rebuilds, index_versions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(docs.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
api_router.include_router(index_rebuilds.router)
api_router.include_router(index_versions.router)

__all__ = ["api_router"]
