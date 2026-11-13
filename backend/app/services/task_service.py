"""Tasks and projects (FR-076..FR-084). A Task is a work item that exists with zero time; time arrives via activities."""

import base64
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rolls_back_on_error
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.time import get_zone, week_start_date
from app.models import Activity, Project, Task, User
from app.models.enums import TaskStatus
from app.repositories.tasks import TasksRepository
from app.repositories.users import UsersRepository
from app.schemas.task import (
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    RollupPoint,
    TaskCreate,
    TaskOut,
    TaskPatch,
    TaskRollup,
)
from app.services import serializers

CLEARABLE = {"project_id", "priority", "due_date", "estimate_minutes", "description"}


def today_for(user: User) -> date:
    return datetime.now(UTC).astimezone(get_zone(user.timezone)).date()


async def task_out(session: AsyncSession, user: User, tasks: list[Task]) -> list[TaskOut]:
    minutes = await TasksRepository(session, user.id).logged_minutes([t.id for t in tasks])
    today = today_for(user)
    out = []
    for t in tasks:
        o = TaskOut.model_validate(t)
        o.logged_minutes = minutes.get(t.id, 0)
        if t.due_date and t.status == TaskStatus.open:
            o.days_left = (t.due_date - today).days
            o.overdue = t.due_date < today
        out.append(o)
    return out


def encode_cursor(ts: datetime, id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{id}".encode()).decode()


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    try:
        ts, id_ = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except Exception as e:  # noqa: BLE001
        raise ValidationFailed("Invalid cursor", path="cursor", rule="invalid") from e


class TaskService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = TasksRepository(session, user.id)

    async def _project(self, project_id: uuid.UUID) -> Project:
        p = await self.repo.get(Project, project_id)
        if p is None:
            raise ValidationFailed("Unknown project", path="project_id", rule="not_found")
        return p

    async def _task(self, task_id: uuid.UUID, *, for_update: bool = False) -> Task:
        t = await self.repo.get(Task, task_id, for_update=for_update)
        if t is None:
            raise NotFound("Task not found")
        return t

    async def _bump(self) -> None:
        await UsersRepository(self.session).bump_revision(self.user.id)

    # ---- tasks
    async def list_tasks(self, *, status, project_id, priority, due_before, has_time, q, limit, cursor) -> tuple[list[TaskOut], str | None]:
        rows = await self.repo.list_tasks(status=status, project_id=project_id, priority=priority, due_before=due_before,
                                          has_time=has_time, q=q, limit=limit, cursor=decode_cursor(cursor))
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None
        return await task_out(self.session, self.user, rows), nxt

    @rolls_back_on_error
    async def create(self, body: TaskCreate) -> TaskOut:
        if body.project_id:
            await self._project(body.project_id)
        t = Task(user_id=self.user.id, **body.model_dump())
        self.session.add(t)
        await self.session.commit()
        await self.session.refresh(t)
        return (await task_out(self.session, self.user, [t]))[0]

    async def detail(self, task_id: uuid.UUID) -> dict:
        t = await self._task(task_id)
        base = (await task_out(self.session, self.user, [t]))[0]
        slices = await self.repo.task_slices(t.id)
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        by_week: dict[date, int] = defaultdict(int)
        for d, m in slices:
            by_week[week_start_date(d, prefs.week_start)] += m
        rollup = TaskRollup(
            total_minutes=sum(m for _, m in slices),
            by_week=[RollupPoint(key=k.isoformat(), minutes=v) for k, v in sorted(by_week.items())],
            by_day=[RollupPoint(key=d.isoformat(), minutes=m) for d, m in slices],
            first_logged=slices[0][0] if slices else None, last_logged=slices[-1][0] if slices else None,
        )
        activities = await serializers.activities_out(self.session, self.user.id, await self.repo.task_activities(t.id))
        return {**base.model_dump(), "rollup": rollup, "activities": activities}

    @rolls_back_on_error
    async def patch(self, task_id: uuid.UUID, body: TaskPatch) -> TaskOut:
        t = await self._task(task_id, for_update=True)
        if body.version is not None and body.version != t.version:
            raise Conflict("This task was changed elsewhere", code="VERSION_CONFLICT", details={"current_version": t.version})
        data = body.model_dump(exclude_unset=True, exclude={"version", "clear", "status"})
        if "project_id" in data and data["project_id"]:
            await self._project(data["project_id"])
        for f in body.clear:
            if f not in CLEARABLE:
                raise ValidationFailed(f"Cannot clear {f}", path="clear", rule="not_clearable")
            data[f] = None
        for k, v in data.items():
            setattr(t, k, v)
        if body.status is not None and body.status != t.status:
            t.status = body.status
            t.completed_at = None if body.status == TaskStatus.open else datetime.now(UTC)
        t.version += 1
        await self.session.commit()
        await self.session.refresh(t)
        return (await task_out(self.session, self.user, [t]))[0]

    @rolls_back_on_error
    async def delete(self, task_id: uuid.UUID) -> None:
        t = await self._task(task_id, for_update=True)
        await self.session.execute(update(Activity).where(Activity.user_id == self.user.id, Activity.task_id == t.id).values(task_id=None))
        t.deleted_at = datetime.now(UTC)
        await self._bump()
        await self.session.commit()

    async def deadlines(self, days: int = 7) -> list[TaskOut]:
        today = today_for(self.user)
        return await task_out(self.session, self.user, await self.repo.open_deadlines(today + timedelta(days=days)))

    # ---- projects
    async def _project_out(self, projects: list[Project]) -> list[ProjectOut]:
        roll = await self.repo.project_rollups([p.id for p in projects])
        return [ProjectOut(id=p.id, name=p.name, color=p.color, archived=p.archived_at is not None,
                           task_count=roll[p.id][0], logged_minutes=roll[p.id][1]) for p in projects]

    async def list_projects(self, archived: bool | None) -> list[ProjectOut]:
        return await self._project_out(await self.repo.projects(archived))

    @rolls_back_on_error
    async def create_project(self, body: ProjectCreate) -> ProjectOut:
        if await self.repo.project_name_taken(body.name):
            raise Conflict("A project with that name exists", code="NAME_TAKEN")
        p = Project(user_id=self.user.id, name=body.name, color=body.color)
        self.session.add(p)
        await self.session.commit()
        return (await self._project_out([p]))[0]

    @rolls_back_on_error
    async def patch_project(self, project_id: uuid.UUID, body: ProjectPatch) -> ProjectOut:
        p = await self.repo.get(Project, project_id)
        if p is None:
            raise NotFound("Project not found")
        if body.name is not None and body.name.lower() != p.name.lower() and await self.repo.project_name_taken(body.name, p.id):
            raise Conflict("A project with that name exists", code="NAME_TAKEN")
        if body.name is not None:
            p.name = body.name
        if body.color is not None:
            p.color = body.color
        if body.archived is not None:
            p.archived_at = datetime.now(UTC) if body.archived else None
        await self._bump()
        await self.session.commit()
        return (await self._project_out([p]))[0]
