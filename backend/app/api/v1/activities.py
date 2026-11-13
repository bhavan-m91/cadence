import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser, Filters, Limit
from app.schemas.activity import (
    ActivityCreate,
    ActivityDetail,
    ActivityOut,
    ActivityPatch,
    BulkIn,
    BulkOut,
    DuplicateIn,
    EventOut,
    MarkDoneIn,
    MergeIn,
    SplitIn,
    SplitOut,
    TagsPut,
)
from app.schemas.common import Envelope, ok
from app.services.activity_service import ActivityService
from app.services.task_service import decode_cursor, encode_cursor

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=Envelope[list[ActivityOut]])
async def list_activities(user: CurrentUser, session: DB, filters: Filters, limit: Limit = 20, cursor: Annotated[str | None, Query()] = None):
    items, more = await ActivityService(session, user).search(filters, limit, decode_cursor(cursor))
    nxt = None
    if more and items:
        last = items[-1]
        nxt = encode_cursor(last.start_at or last.window_start_at, last.id)
    return ok(items, next_cursor=nxt)


@router.post("", response_model=Envelope[ActivityOut], status_code=201)
async def create_activity(body: ActivityCreate, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).create(body))


@router.post("/merge", response_model=Envelope[ActivityOut])
async def merge_activities(body: MergeIn, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).merge(body))


@router.post("/bulk", response_model=Envelope[BulkOut])
async def bulk(body: BulkIn, user: CurrentUser, session: DB):
    return ok({"updated": await ActivityService(session, user).bulk(body)})


@router.get("/{activity_id}", response_model=Envelope[ActivityDetail])
async def get_activity(activity_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).detail(activity_id))


@router.patch("/{activity_id}", response_model=Envelope[ActivityOut])
async def patch_activity(activity_id: uuid.UUID, body: ActivityPatch, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).patch(activity_id, body))


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(activity_id: uuid.UUID, user: CurrentUser, session: DB):
    await ActivityService(session, user).delete(activity_id)
    return Response(status_code=204)


@router.post("/{activity_id}/restore", response_model=Envelope[ActivityOut])
async def restore_activity(activity_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).restore(activity_id))


@router.post("/{activity_id}/split", response_model=Envelope[SplitOut])
async def split_activity(activity_id: uuid.UUID, body: SplitIn, user: CurrentUser, session: DB):
    original, created = await ActivityService(session, user).split(activity_id, body.at)
    return ok({"original": original, "created": created})


@router.post("/{activity_id}/duplicate", response_model=Envelope[ActivityOut], status_code=201)
async def duplicate_activity(activity_id: uuid.UUID, user: CurrentUser, session: DB, body: DuplicateIn | None = None):
    return ok(await ActivityService(session, user).duplicate(activity_id, body.start_at if body else None))


@router.put("/{activity_id}/tags", response_model=Envelope[ActivityOut])
async def put_tags(activity_id: uuid.UUID, body: TagsPut, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).set_tags(activity_id, body.tag_ids))


@router.get("/{activity_id}/events", response_model=Envelope[list[EventOut]])
async def events(activity_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await ActivityService(session, user).events(activity_id))


@router.post("/{activity_id}/mark-done", response_model=Envelope[ActivityOut])
async def mark_done(activity_id: uuid.UUID, user: CurrentUser, session: DB, body: MarkDoneIn | None = None):
    return ok(await ActivityService(session, user).mark_done(activity_id, body.start_at if body else None, body.end_at if body else None))
