import uuid

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.schemas.common import Envelope, ok
from app.schemas.task import ProjectCreate, ProjectOut, ProjectPatch
from app.services.task_service import TaskService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Envelope[list[ProjectOut]])
async def list_projects(user: CurrentUser, session: DB, archived: bool | None = None):
    return ok(await TaskService(session, user).list_projects(archived))


@router.post("", response_model=Envelope[ProjectOut], status_code=201)
async def create_project(body: ProjectCreate, user: CurrentUser, session: DB):
    return ok(await TaskService(session, user).create_project(body))


@router.patch("/{project_id}", response_model=Envelope[ProjectOut])
async def patch_project(project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser, session: DB):
    return ok(await TaskService(session, user).patch_project(project_id, body))
