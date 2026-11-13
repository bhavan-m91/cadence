from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.models.enums import IdealKind
from app.schemas.common import Envelope, ok
from app.schemas.ideal import IdealOverviewOut, IdealSaveIn, IdealTemplateOut, ProgressOut
from app.services.ideal_service import IdealService

router = APIRouter(prefix="/ideal", tags=["ideal"])
On = Annotated[date | None, Query(alias="on")]


@router.get("/day", response_model=Envelope[IdealOverviewOut])
async def get_day(user: CurrentUser, session: DB, on: On = None):
    return ok(await IdealService(session, user).overview(IdealKind.day, on))


@router.put("/day", response_model=Envelope[IdealTemplateOut])
async def put_day(body: IdealSaveIn, user: CurrentUser, session: DB, dry_run: bool = False):
    return ok(await IdealService(session, user).save(IdealKind.day, body, dry_run))


@router.get("/week", response_model=Envelope[IdealOverviewOut])
async def get_week(user: CurrentUser, session: DB, on: On = None):
    return ok(await IdealService(session, user).overview(IdealKind.week, on))


@router.put("/week", response_model=Envelope[IdealTemplateOut])
async def put_week(body: IdealSaveIn, user: CurrentUser, session: DB, dry_run: bool = False):
    return ok(await IdealService(session, user).save(IdealKind.week, body, dry_run))


@router.get("/progress", response_model=Envelope[ProgressOut])
async def progress(user: CurrentUser, session: DB, on: On = None, scope: Literal["day", "week"] = "week"):
    return ok(await IdealService(session, user).progress(scope, on))
