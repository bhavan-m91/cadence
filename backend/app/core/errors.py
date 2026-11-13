"""Typed application errors and the single mapping to the error envelope (PRD 4.3, 7.1)."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        status: int | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message or code or self.code)
        self.message = message or (code or self.code)
        if code:
            self.code = code
        if status:
            self.status = status
        self.details = details or {}
        self.headers = headers or {}


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Not found", **kw: Any):
        super().__init__(message, **kw)


class Unauthenticated(AppError):
    status = 401
    code = "UNAUTHENTICATED"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class ValidationFailed(AppError):
    status = 422
    code = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation failed", *, path: str = "", rule: str = "invalid", code=None, **kw):
        details = kw.pop("details", None) or {}
        if path:
            details = {"fields": [{"path": path, "rule": rule, "message": message}], **details}
        super().__init__(message, code=code, details=details, **kw)


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int, message: str = "Too many requests"):
        super().__init__(
            message, headers={"Retry-After": str(max(1, retry_after))}, details={"retry_after": retry_after}
        )


def _body(request: Request, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            fields.append({"path": ".".join(loc), "rule": err["type"], "message": err["msg"]})
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Validation failed", {"fields": fields}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(request, code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", path=request.url.path)
        return JSONResponse(_body(request, "INTERNAL", "Something went wrong"), status_code=500)
