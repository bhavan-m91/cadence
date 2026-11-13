import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser
from app.schemas.common import Envelope, ok
from app.schemas.taxonomy import AliasesIn, MergeIn, TagCreate, TagMergeOut, TagOut, TagPatch
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=Envelope[list[TagOut]])
async def list_tags(user: CurrentUser, session: DB, archived: bool = False, q: str | None = None, from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None):
    return ok(await TagService(session, user).list_tags(archived, q, from_, to))


@router.post("", response_model=Envelope[TagOut], status_code=201)
async def create_tag(body: TagCreate, user: CurrentUser, session: DB):
    return ok(await TagService(session, user).create(body))


@router.get("/{tag_id}")
async def get_tag(tag_id: uuid.UUID, user: CurrentUser, session: DB, from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None):
    return ok(await TagService(session, user).detail(tag_id, from_, to))


@router.patch("/{tag_id}", response_model=Envelope[TagOut])
async def patch_tag(tag_id: uuid.UUID, body: TagPatch, user: CurrentUser, session: DB):
    return ok(await TagService(session, user).patch(tag_id, body))


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: uuid.UUID, user: CurrentUser, session: DB):
    await TagService(session, user).delete(tag_id)
    return Response(status_code=204)


@router.post("/{tag_id}/merge", response_model=Envelope[TagMergeOut])
async def merge_tag(tag_id: uuid.UUID, body: MergeIn, user: CurrentUser, session: DB):
    return ok(await TagService(session, user).merge(tag_id, body.target_id, body.preview))


@router.put("/{tag_id}/aliases", response_model=Envelope[list[str]])
async def put_aliases(tag_id: uuid.UUID, body: AliasesIn, user: CurrentUser, session: DB):
    return ok(await TagService(session, user).put_aliases(tag_id, body))
