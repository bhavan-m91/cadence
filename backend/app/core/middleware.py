"""Request id, access log, body-size limit and security headers as one pure-ASGI layer."""

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger()

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"cache-control": b"no-store",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope["headers"]}
        request_id = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-request-id", request_id.encode()))
                present = {k.lower() for k, _ in hdrs}
                for k, v in SECURITY_HEADERS.items():
                    if k not in present:
                        hdrs.append((k, v))
                message = {**message, "headers": hdrs}
            await send(message)

        length = headers.get(b"content-length")
        if length and length.isdigit() and int(length) > self.max_body_bytes and not scope["path"].endswith("/transcriptions"):
            body = b'{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body too large","details":{},"request_id":"%s"}}' % request_id.encode()
            await send_wrapper({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
            await send_wrapper({"type": "http.response.body", "body": body})
            return

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if scope["path"] not in ("/api/v1/healthz",):
                log.info(
                    "request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status_holder["status"],
                    ms=round((time.perf_counter() - started) * 1000, 1),
                )
