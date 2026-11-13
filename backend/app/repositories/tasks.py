import uuid
from datetime import date

from sqlalchemy import func, select

from app.models import Activity, ActivityDaySlice, Project, Task
from app.models.enums import TaskStatus
from app.repositories.base import UserScopedRepository


class TasksRepository(UserScopedRepository):
    async def list_tasks(self, *, status=None, project_id=None, priority=None, due_before: date | None = None,
                         has_time: bool | None = None, q: str | None = None, limit: int = 50, cursor=None) -> list[Task]:
        stmt = select(Task).where(Task.user_id == self.user_id, Task.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Task.status == status)
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if due_before:
            stmt = stmt.where(Task.due_date <= due_before)
        if q:
            stmt = stmt.where(Task.title.ilike(f"%{q}%"))
        if has_time is not None:
            linked = select(Activity.task_id).where(Activity.user_id == self.user_id, Activity.task_id.is_not(None), Activity.deleted_at.is_(None))
            stmt = stmt.where(Task.id.in_(linked) if has_time else Task.id.not_in(linked))
        if cursor:
            created_at, tid = cursor
            stmt = stmt.where((Task.created_at < created_at) | ((Task.created_at == created_at) & (Task.id > tid)))
        stmt = stmt.order_by(Task.created_at.desc(), Task.id).limit(limit + 1)
        return list((await self.session.execute(stmt)).scalars())

    async def logged_minutes(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not task_ids:
            return {}
        stmt = (
            select(Activity.task_id, func.coalesce(func.sum(ActivityDaySlice.minutes), 0))
            .join(ActivityDaySlice, ActivityDaySlice.activity_id == Activity.id)
            .where(Activity.user_id == self.user_id, Activity.task_id.in_(task_ids))
            .group_by(Activity.task_id)
        )
        return {tid: int(m) for tid, m in (await self.session.execute(stmt)).all()}

    async def task_slices(self, task_id: uuid.UUID) -> list[tuple[date, int]]:
        stmt = (
            select(ActivityDaySlice.local_date, func.sum(ActivityDaySlice.minutes))
            .join(Activity, Activity.id == ActivityDaySlice.activity_id)
            .where(Activity.user_id == self.user_id, Activity.task_id == task_id)
            .group_by(ActivityDaySlice.local_date)
            .order_by(ActivityDaySlice.local_date)
        )
        return [(d, int(m)) for d, m in (await self.session.execute(stmt)).all()]

    async def task_activities(self, task_id: uuid.UUID) -> list[Activity]:
        stmt = select(Activity).where(Activity.user_id == self.user_id, Activity.task_id == task_id, Activity.deleted_at.is_(None)).order_by(Activity.start_at.desc().nulls_last(), Activity.id)
        return list((await self.session.execute(stmt)).scalars())

    async def projects(self, archived: bool | None = None) -> list[Project]:
        stmt = select(Project).where(Project.user_id == self.user_id)
        if archived is True:
            stmt = stmt.where(Project.archived_at.is_not(None))
        elif archived is False or archived is None:
            stmt = stmt.where(Project.archived_at.is_(None))
        return list((await self.session.execute(stmt.order_by(func.lower(Project.name)))).scalars())

    async def project_name_taken(self, name: str, exclude: uuid.UUID | None = None) -> bool:
        stmt = select(func.count()).select_from(Project).where(Project.user_id == self.user_id, func.lower(Project.name) == name.lower())
        if exclude:
            stmt = stmt.where(Project.id != exclude)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def project_rollups(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """project_id -> (task_count, logged_minutes). Activity project wins; falls back to the task's project."""
        out = {p: (0, 0) for p in project_ids}
        if not project_ids:
            return out
        counts = (await self.session.execute(
            select(Task.project_id, func.count()).where(Task.user_id == self.user_id, Task.deleted_at.is_(None), Task.project_id.in_(project_ids)).group_by(Task.project_id))).all()
        minutes = (await self.session.execute(
            select(Activity.project_id, func.coalesce(func.sum(ActivityDaySlice.minutes), 0))
            .join(ActivityDaySlice, ActivityDaySlice.activity_id == Activity.id)
            .where(Activity.user_id == self.user_id, Activity.project_id.in_(project_ids)).group_by(Activity.project_id))).all()
        for pid, c in counts:
            out[pid] = (c, out[pid][1])
        for pid, m in minutes:
            out[pid] = (out[pid][0], int(m))
        return out

    async def open_deadlines(self, until: date) -> list[Task]:
        stmt = select(Task).where(Task.user_id == self.user_id, Task.deleted_at.is_(None), Task.status == TaskStatus.open, Task.due_date.is_not(None), Task.due_date <= until).order_by(Task.due_date)
        return list((await self.session.execute(stmt)).scalars())
