from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.schemas.common import ErrorEnvelope


def _init_sentry(dsn: str, env: str) -> None:
    try:
        import sentry_sdk
    except ImportError:  # sentry is optional locally
        return
    sentry_sdk.init(dsn=dsn, environment=env, send_default_pii=False, max_request_body_size="never", traces_sample_rate=0.05)


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.app_env)
    if s.sentry_dsn:
        _init_sentry(s.sentry_dsn, s.app_env)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await dispose_engine()

    app = FastAPI(
        title="Cadence API", version="0.1.0", lifespan=lifespan,
        description="Personal time tracker and life analytics. All responses use {data, meta} or {error}.",
        responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope},
                   422: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id", "If-None-Match"],
        expose_headers=["X-Request-Id", "Retry-After", "ETag"],
    )
    app.add_middleware(RequestContextMiddleware, max_body_bytes=s.max_body_bytes)
    app.include_router(api_router)
    return app


app = create_app()
