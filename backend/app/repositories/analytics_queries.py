"""Named aggregate reads for analytics. Everything reads `activity_day_slices` (D-15), which only holds confirmed, actual,
non-deleted activities; the joins repeat those predicates so a drifted slice can never leak a draft or a plan (AC-064, AC-065)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.analytics.sleep import SleepActivity
from app.core.time import day_start
from app.models import Activity, ActivityDaySlice, ActivityTag, Category, Project, Tag, Task
from app.models.enums import ActivityKind, ActivityStatus, Placement, RootKind
from app.repositories.base import UserScopedRepository


@dataclass
class SliceRow:
    local_date: date
    category_id: uuid.UUID
    minutes: int
    is_placed: bool
    certainty: str
    location: str | None
    activity_id: uuid.UUID
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    start_at: datetime | None
    end_at: datetime | None


class AnalyticsQueries(UserScopedRepository):
    def _live(self, stmt):
        return stmt.where(ActivityDaySlice.user_id == self.user_id, Activity.status == ActivityStatus.confirmed,
                          Activity.kind == ActivityKind.actual, Activity.deleted_at.is_(None))

    async def slices(self, from_date: date, to_date: date, allowed: set[uuid.UUID] | None = None) -> list[SliceRow]:
        stmt = self._live(
            select(ActivityDaySlice, Activity.task_id, Activity.project_id)
            .join(Activity, Activity.id == ActivityDaySlice.activity_id)
            .where(ActivityDaySlice.local_date.between(from_date, to_date))
        )
        rows = (await self.session.execute(stmt)).all()
        return [SliceRow(s.local_date, s.category_id, s.minutes, s.is_placed, s.time_certainty.value, s.location_type.value if s.location_type else None,
                         s.activity_id, task_id, project_id, s.slice_start_at, s.slice_end_at)
                for s, task_id, project_id in rows if allowed is None or s.activity_id in allowed]

    async def tags_by_activity(self, from_date: date, to_date: date) -> dict[uuid.UUID, list[uuid.UUID]]:
        stmt = (
            self._live(select(ActivityTag.activity_id, ActivityTag.tag_id)
                       .join(ActivityDaySlice, ActivityDaySlice.activity_id == ActivityTag.activity_id)
                       .join(Activity, Activity.id == ActivityDaySlice.activity_id)
                       .where(ActivityDaySlice.local_date.between(from_date, to_date)))
            .distinct()
        )
        out: dict[uuid.UUID, list[uuid.UUID]] = {}
        for aid, tid in (await self.session.execute(stmt)).all():
            out.setdefault(aid, []).append(tid)
        return out

    async def sleep_activities(self, from_date: date, to_date: date, tz: ZoneInfo) -> list[SleepActivity]:
        """Sleep-root activities whose wake date (local date of `end_at`) falls in the range. Duration-only sleep uses its own date."""
        lo, hi = day_start(from_date, tz), day_start(date.fromordinal(to_date.toordinal() + 1), tz)
        stmt = (
            select(Activity)
            .join(Category, Category.id == Activity.category_id)
            .where(Activity.user_id == self.user_id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual,
                   Activity.deleted_at.is_(None), Category.root_kind == RootKind.sleep,
                   or_(and_(Activity.placement == Placement.placed, Activity.end_at > lo, Activity.end_at <= hi),
                       and_(Activity.placement == Placement.unplaced, Activity.local_date.between(from_date, to_date))))
        )
        out = []
        for a in (await self.session.execute(stmt)).scalars():
            out.append(SleepActivity(a.duration_minutes or 0, a.placement == Placement.placed, a.start_at, a.end_at, a.local_date))
        return out

    async def focus_by_day(self, from_date: date, to_date: date) -> dict[date, int]:
        stmt = self._live(
            select(ActivityDaySlice.local_date, func.sum(ActivityDaySlice.minutes))
            .join(Activity, Activity.id == ActivityDaySlice.activity_id)
            .join(Category, Category.id == ActivityDaySlice.category_id)
            .where(ActivityDaySlice.local_date.between(from_date, to_date), Category.counts_as_focus.is_(True))
            .group_by(ActivityDaySlice.local_date)
        )
        return {d: int(m) for d, m in (await self.session.execute(stmt)).all()}

    async def first_logged_date(self) -> date | None:
        return (await self.session.execute(select(func.min(ActivityDaySlice.local_date)).where(ActivityDaySlice.user_id == self.user_id))).scalar_one()

    async def filtered_activity_ids(self, stmt) -> set[uuid.UUID]:
        return {i for (i,) in (await self.session.execute(stmt)).all()}

    async def categories(self) -> dict[uuid.UUID, Category]:
        return {c.id: c for c in (await self.session.execute(select(Category).where(Category.user_id == self.user_id))).scalars()}

    async def tags(self) -> dict[uuid.UUID, Tag]:
        return {t.id: t for t in (await self.session.execute(select(Tag).where(Tag.user_id == self.user_id))).scalars()}

    async def tasks(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Task]:
        return {t.id: t for t in await self.get_many(Task, ids)}

    async def projects(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Project]:
        return {p.id: p for p in await self.get_many(Project, ids)}
