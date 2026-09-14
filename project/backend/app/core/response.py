"""统一响应包裹格式与业务异常（api_document 1.3）。

所有同步接口统一返回：``{"code": int, "message": str, "data": any}``
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def success(data: Any = None, message: str = "操作成功") -> dict[str, Any]:
    return {"code": 200, "message": message, "data": data}


def failure(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}


class APIException(Exception):
    """业务异常：抛出后由全局处理器转换为统一 Envelope。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class BadRequest(APIException):
    def __init__(self, message: str = "参数校验失败", data: Any = None) -> None:
        super().__init__(400, message, data)


class Unauthorized(APIException):
    def __init__(self, message: str = "登录状态已失效，请重新登录", data: Any = None) -> None:
        super().__init__(401, message, data)


class Forbidden(APIException):
    def __init__(self, message: str = "权限不足，无法执行该操作", data: Any = None) -> None:
        super().__init__(403, message, data)


class NotFound(APIException):
    def __init__(self, message: str = "资源不存在", data: Any = None) -> None:
        super().__init__(404, message, data)


class ServerError(APIException):
    def __init__(self, message: str = "服务器内部异常，请稍后重试", data: Any = None) -> None:
        super().__init__(500, message, data)


# ------------------------------------------------------------
# 全局异常处理器
# ------------------------------------------------------------

_HTTP_MESSAGES = {
    401: "登录状态已失效，请重新登录",
    403: "权限不足，无法执行该操作",
    404: "资源不存在",
    405: "请求方法不被支持",
    413: "上传内容超出大小限制",
    500: "服务器内部异常，请稍后重试",
}


def register_exception_handlers(app) -> None:
    @app.exception_handler(APIException)
    async def _api_exception_handler(_: Request, exc: APIException):
        return JSONResponse(
            status_code=exc.code if 100 <= exc.code < 600 else 500,
            content=failure(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException):
        code = exc.status_code
        detail = exc.detail if isinstance(exc.detail, str) else None
        message = detail or _HTTP_MESSAGES.get(code, "请求失败")
        # FastAPI 默认英文提示统一转成中文（PRD 5.4 友好交互）
        if message in {"Not Found", "Method Not Allowed", "Not authenticated", "Forbidden"}:
            message = _HTTP_MESSAGES.get(code, message)
        return JSONResponse(status_code=code, content=failure(code, message))

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        message = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        return JSONResponse(status_code=400, content=failure(400, message))

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(_: Request, exc: Exception):  # pragma: no cover
        import logging

        logging.getLogger("app").exception("未捕获异常: %s", exc)
        return JSONResponse(status_code=500, content=failure(500, "服务器内部异常，请稍后重试"))
