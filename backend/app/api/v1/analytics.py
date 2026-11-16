import hashlib
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import DB, CurrentUser, Filters
from app.core import clock
from app.schemas.analytics import BreakdownOut, DayAnalytics, OverviewOut, TrendsOut, WeekAnalytics
from app.schemas.common import Envelope, ok
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])
Lens = Literal["all", "work", "personal"]


def etag(request: Request, user, svc: AnalyticsService, live: bool) -> str:
    """FR-144: the user's data revision plus the request. A range that includes today also changes with the clock, so it carries the minute."""
    minute = int(clock.now().timestamp() // 60) if live else 0
    raw = f"{user.data_revision}|{user.timezone}|{request.url.path}?{request.url.query}|{minute}"
    return f'W/"{hashlib.sha1(raw.encode()).hexdigest()[:20]}"'


def cached(request: Request, response: Response, tag: str) -> Response | None:
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = "private, no-cache"
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "private, no-cache"})
    return None


@router.get("/day/{day}", response_model=Envelope[DayAnalytics])
async def day(day: date, request: Request, response: Response, user: CurrentUser, session: DB, lens: Lens = "all"):
    svc = AnalyticsService(session, user, lens)
    if (hit := cached(request, response, etag(request, user, svc, svc.touches_today(day, day)))):
        return hit
    return ok(await svc.day(day))


@router.get("/week/{week_start}", response_model=Envelope[WeekAnalytics])
async def week(week_start: date, request: Request, response: Response, user: CurrentUser, session: DB, lens: Lens = "all"):
    svc = AnalyticsService(session, user, lens)
    if (hit := cached(request, response, etag(request, user, svc, True))):
        return hit
    return ok(await svc.week(week_start))


@router.get("/overview", response_model=Envelope[OverviewOut])
async def overview(request: Request, response: Response, user: CurrentUser, session: DB, scope: Literal["day", "week"] = "week", anchor: date | None = None, lens: Lens = "all"):
    svc = AnalyticsService(session, user, lens)
    if (hit := cached(request, response, etag(request, user, svc, True))):
        return hit
    return ok(await svc.overview(scope, anchor))


@router.get("/breakdown", response_model=Envelope[BreakdownOut])
async def breakdown(request: Request, response: Response, user: CurrentUser, session: DB, filters: Filters,
                    from_: Annotated[date, Query(alias="from")], to: date, by: Literal["category", "tag", "task", "project"] = "category", lens: Lens = "all"):
    svc = AnalyticsService(session, user, lens)
    if (hit := cached(request, response, etag(request, user, svc, svc.touches_today(from_, to)))):
        return hit
    return ok(await svc.breakdown(from_, to, by, filters))


@router.get("/trends", response_model=Envelope[TrendsOut])
async def trends(request: Request, response: Response, user: CurrentUser, session: DB,
                 metric: Literal["adherence", "coverage", "sleep", "focus"], granularity: Literal["day", "week"] = "week", periods: int = 8, lens: Lens = "all"):
    svc = AnalyticsService(session, user, lens)
    if (hit := cached(request, response, etag(request, user, svc, True))):
        return hit
    return ok(await svc.trends(metric, granularity, periods))
