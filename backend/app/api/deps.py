import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import RateLimited, Unauthenticated, ValidationFailed
from app.core.rate_limit import limiter
from app.core.security import decode_access_token
from app.models import User
from app.models.enums import ActivityKind, ActivityStatus, TimeCertainty
from app.repositories.activities import ActivityFilters
from app.repositories.taxonomy import TaxonomyRepository

bearer = HTTPBearer(auto_error=False)
DB = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    if get_settings().is_production:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def get_current_user(
    session: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> User:
    if creds is None:
        raise Unauthenticated("Sign in to continue")
    user_id = decode_access_token(creds.credentials)
    user = await session.get(User, user_id)
    if user is None:
        raise Unauthenticated("Sign in to continue")
    s = get_settings()
    key = f"api:{user.id}"
    if limiter.hit(key, 60) > s.api_rate_limit_per_minute:
        raise RateLimited(limiter.retry_after(key, 60))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]


async def activity_filters(
    session: DB, user: CurrentUser, from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None, category_id: uuid.UUID | None = None,
    tag_ids: Annotated[list[uuid.UUID] | None, Query()] = None, tag_mode: Annotated[str, Query(pattern="^(any|all)$")] = "any",
    task_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None, status: ActivityStatus | None = None,
    kind: ActivityKind | None = None, certainty: TimeCertainty | None = None, needs_review: bool | None = None,
    lens: Annotated[str, Query(pattern="^(all|work|personal)$")] = "all",
) -> ActivityFilters:
    if from_ and to and (to - from_).days > 366:
        raise ValidationFailed("Range is limited to 366 days", path="to", rule="range_too_long")
    category_ids = None
    if category_id:
        repo = TaxonomyRepository(session, user.id)
        cat = await repo.category(category_id)
        if cat is None:
            raise ValidationFailed("Unknown category", path="category_id", rule="not_found")
        category_ids = [c.id for c in await repo.subtree(cat)]
    return ActivityFilters(from_date=from_, to_date=to, q=q, category_ids=category_ids, tag_ids=tag_ids or [], tag_mode=tag_mode,
                           task_id=task_id, project_id=project_id, status=status, kind=kind, certainty=certainty, needs_review=needs_review,
                           root_kinds={"work": ["work"], "personal": ["personal", "sleep"]}.get(lens))


Filters = Annotated[ActivityFilters, Depends(activity_filters)]
