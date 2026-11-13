import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser
from app.schemas.common import Envelope, ok
from app.schemas.taxonomy import (
    CategoryCreate,
    CategoryMergeOut,
    CategoryNode,
    CategoryOut,
    CategoryPatch,
    MergeIn,
)
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=Envelope[list[CategoryNode]])
async def tree(user: CurrentUser, session: DB, include_archived: bool = False):
    return ok(await CategoryService(session, user).tree(include_archived))


@router.post("", response_model=Envelope[CategoryOut], status_code=201)
async def create_category(body: CategoryCreate, user: CurrentUser, session: DB):
    return ok(await CategoryService(session, user).create(body))


@router.patch("/{category_id}", response_model=Envelope[CategoryOut])
async def patch_category(category_id: uuid.UUID, body: CategoryPatch, user: CurrentUser, session: DB):
    return ok(await CategoryService(session, user).update(category_id, body))


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: uuid.UUID, user: CurrentUser, session: DB):
    await CategoryService(session, user).delete(category_id)
    return Response(status_code=204)


@router.post("/{category_id}/merge", response_model=Envelope[CategoryMergeOut])
async def merge_category(category_id: uuid.UUID, body: MergeIn, user: CurrentUser, session: DB):
    return ok(await CategoryService(session, user).merge(category_id, body.target_id, body.preview))
