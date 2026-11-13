import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser, Limit
from app.models.enums import TaskStatus
from app.schemas.common import Envelope, ok
from app.schemas.task import TaskCreate, TaskOut, TaskPatch
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=Envelope[list[TaskOut]])
async def list_tasks(
    user: CurrentUser, session: DB, status: TaskStatus | None = None, project_id: uuid.UUID | None = None,
    priority: Annotated[int | None, Query(ge=0, le=3)] = None, due_before: date | None = None, has_time: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None, limit: Limit = 50, cursor: str | None = None,
):
    items, nxt = await TaskService(session, user).list_tasks(status=status, project_id=project_id, priority=priority, due_before=due_before,
                                                      has_time=has_time, q=q, limit=limit, cursor=cursor)
    return ok(items, next_cursor=nxt)


@router.post("", response_model=Envelope[TaskOut], status_code=201)
async def create_task(body: TaskCreate, user: CurrentUser, session: DB):
    return ok(await TaskService(session, user).create(body))


@router.get("/{task_id}")
async def get_task(task_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await TaskService(session, user).detail(task_id))


@router.patch("/{task_id}", response_model=Envelope[TaskOut])
async def patch_task(task_id: uuid.UUID, body: TaskPatch, user: CurrentUser, session: DB):
    return ok(await TaskService(session, user).patch(task_id, body))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, user: CurrentUser, session: DB):
    await TaskService(session, user).delete(task_id)
    return Response(status_code=204)
