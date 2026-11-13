from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser, Filters
from app.schemas.common import Envelope, ok
from app.schemas.timeline import TimelineOut
from app.services.timeline_service import TimelineService

router = APIRouter(tags=["timeline"])


@router.get("/timeline", response_model=Envelope[TimelineOut])
async def timeline(user: CurrentUser, session: DB, filters: Filters, from_: Annotated[date, Query(alias="from")], to: date, ideal: bool = False):
    has_filters = any([filters.q, filters.category_ids is not None, filters.tag_ids, filters.task_id, filters.project_id,
                       filters.certainty, filters.needs_review is not None])
    return ok(await TimelineService(session, user).build(from_, to, filters if has_filters else None, ideal))
