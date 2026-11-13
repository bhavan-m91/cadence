"""Safe retries for `process` and `review/commit` (PRD 7.1): same key + same body replays the stored response;
same key + different body is refused."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import IdempotencyKey


def request_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def run_idempotent(session: AsyncSession, user_id, key: str | None, endpoint: str, payload: Any,
                         fn: Callable[[], Awaitable[tuple[int, dict]]], *, required: bool = True) -> tuple[int, dict]:
    if not key:
        if required:
            raise AppError("Send an Idempotency-Key header", code="IDEMPOTENCY_KEY_REQUIRED", status=422)
        return await fn()
    if len(key) > 64:
        raise AppError("Idempotency-Key is too long", code="IDEMPOTENCY_KEY_INVALID", status=422)
    digest = request_hash(payload)
    row = await session.get(IdempotencyKey, (user_id, key, endpoint))
    if row is not None:
        if row.request_hash != digest:
            raise AppError("That Idempotency-Key was used with a different request", code="IDEMPOTENCY_MISMATCH", status=422)
        return row.response_status, row.response_body
    status, body = await fn()
    stmt = insert(IdempotencyKey).values(user_id=user_id, key=key, endpoint=endpoint, request_hash=digest, response_status=status,
                                         response_body=body).on_conflict_do_nothing()
    await session.execute(stmt)
    await session.commit()
    return status, body
