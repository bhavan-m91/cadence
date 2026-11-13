import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import and_, delete, exists, func, or_, select

from app.models import Activity, ActivityDaySlice, ActivityEvent, ActivityTag, Tag
from app.models.enums import (
    ActivityEventType,
    ActivityKind,
    ActivityStatus,
    EventActor,
    Placement,
    TimeCertainty,
)
from app.repositories.base import UserScopedRepository


@dataclass
class ActivityFilters:
    from_date: date | None = None
    to_date: date | None = None
    q: str | None = None
    category_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] = field(default_factory=list)
    tag_mode: str = "any"
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    status: ActivityStatus | None = None
    kind: ActivityKind | None = None
    certainty: TimeCertainty | None = None
    needs_review: bool | None = None


def sort_key():
    return func.coalesce(Activity.start_at, Activity.window_start_at)


class ActivitiesRepository(UserScopedRepository):
    async def get_deleted(self, id: uuid.UUID) -> Activity | None:
        stmt = select(Activity).where(Activity.id == id, Activity.user_id == self.user_id, Activity.deleted_at.is_not(None)).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_overlaps(self, start: datetime, end: datetime, exclude_ids: list[uuid.UUID] | None = None) -> list[Activity]:
        stmt = select(Activity).where(
            Activity.user_id == self.user_id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual,
            Activity.placement == Placement.placed, Activity.deleted_at.is_(None), Activity.start_at < end, Activity.end_at > start,
        )
        if exclude_ids:
            stmt = stmt.where(Activity.id.not_in(exclude_ids))
        # Pure read of persisted state: never flush half-applied edits (they would trip the DB constraint with a 500).
        with self.session.no_autoflush:
            return list((await self.session.execute(stmt.order_by(Activity.start_at))).scalars())

    def _apply(self, stmt, f: ActivityFilters):
        stmt = stmt.where(Activity.user_id == self.user_id, Activity.deleted_at.is_(None))
        stmt = stmt.where(Activity.status == (f.status or ActivityStatus.confirmed))
        if f.from_date:
            stmt = stmt.where(Activity.local_date >= f.from_date)
        if f.to_date:
            stmt = stmt.where(Activity.local_date <= f.to_date)
        if f.q:
            like = f"%{f.q}%"
            stmt = stmt.where(or_(Activity.title.ilike(like), Activity.description.ilike(like), Activity.source_quote.ilike(like)))
        if f.category_ids is not None:
            stmt = stmt.where(Activity.category_id.in_(f.category_ids))
        if f.tag_ids:
            if f.tag_mode == "all":
                stmt = stmt.where(
                    select(func.count(func.distinct(ActivityTag.tag_id))).where(ActivityTag.activity_id == Activity.id, ActivityTag.tag_id.in_(f.tag_ids)).scalar_subquery() == len(set(f.tag_ids))
                )
            else:
                stmt = stmt.where(exists().where(ActivityTag.activity_id == Activity.id, ActivityTag.tag_id.in_(f.tag_ids)))
        if f.task_id:
            stmt = stmt.where(Activity.task_id == f.task_id)
        if f.project_id:
            stmt = stmt.where(Activity.project_id == f.project_id)
        if f.kind:
            stmt = stmt.where(Activity.kind == f.kind)
        if f.certainty:
            stmt = stmt.where(Activity.time_certainty == f.certainty)
        if f.needs_review is not None:
            stmt = stmt.where(Activity.needs_review == f.needs_review)
        return stmt

    async def search(self, f: ActivityFilters, limit: int, cursor: tuple[datetime, uuid.UUID] | None) -> list[Activity]:
        stmt = self._apply(select(Activity), f)
        key = sort_key()
        if cursor:
            c_ts, c_id = cursor
            stmt = stmt.where(or_(key < c_ts, and_(key == c_ts, Activity.id > c_id)))
        stmt = stmt.order_by(key.desc(), Activity.id).limit(limit + 1)
        return list((await self.session.execute(stmt)).scalars())

    async def tags_for(self, activity_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[ActivityTag, Tag]]]:
        out: dict[uuid.UUID, list[tuple[ActivityTag, Tag]]] = {a: [] for a in activity_ids}
        if activity_ids:
            stmt = select(ActivityTag, Tag).join(Tag, Tag.id == ActivityTag.tag_id).where(ActivityTag.activity_id.in_(activity_ids)).order_by(Tag.name)
            for link, tag in (await self.session.execute(stmt)).all():
                out[link.activity_id].append((link, tag))
        return out

    async def tag_links(self, activity_id: uuid.UUID) -> list[ActivityTag]:
        return list((await self.session.execute(select(ActivityTag).where(ActivityTag.activity_id == activity_id))).scalars())

    def add_event(self, activity_id: uuid.UUID, event: ActivityEventType, actor: EventActor = EventActor.user, payload: dict | None = None) -> None:
        self.session.add(ActivityEvent(activity_id=activity_id, user_id=self.user_id, event_type=event, actor=actor, payload=payload))

    async def events(self, activity_id: uuid.UUID) -> list[ActivityEvent]:
        stmt = select(ActivityEvent).where(ActivityEvent.activity_id == activity_id, ActivityEvent.user_id == self.user_id).order_by(ActivityEvent.created_at, ActivityEvent.id)
        return list((await self.session.execute(stmt)).scalars())

    async def also_tagged(self, activity: Activity, tag_ids: list[uuid.UUID], from_date: date, to_date: date, limit: int = 8) -> list[Activity]:
        if not tag_ids:
            return []
        stmt = (
            select(Activity)
            .where(
                Activity.user_id == self.user_id, Activity.deleted_at.is_(None), Activity.id != activity.id,
                Activity.status == ActivityStatus.confirmed, Activity.local_date.between(from_date, to_date),
                exists().where(ActivityTag.activity_id == Activity.id, ActivityTag.tag_id.in_(tag_ids)),
            )
            .order_by(sort_key().desc()).limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    # ---- slices
    async def delete_slices(self, activity_id: uuid.UUID) -> None:
        await self.session.execute(delete(ActivityDaySlice).where(ActivityDaySlice.activity_id == activity_id))

    async def slices_in_range(self, from_date: date, to_date: date) -> list[tuple[ActivityDaySlice, Activity]]:
        stmt = (
            select(ActivityDaySlice, Activity)
            .join(Activity, Activity.id == ActivityDaySlice.activity_id)
            .where(ActivityDaySlice.user_id == self.user_id, ActivityDaySlice.local_date.between(from_date, to_date))
            .order_by(ActivityDaySlice.slice_start_at.nulls_last(), Activity.id)
        )
        return [(s, a) for s, a in (await self.session.execute(stmt)).all()]

    async def planned_in_range(self, start: datetime, end: datetime) -> list[Activity]:
        stmt = select(Activity).where(
            Activity.user_id == self.user_id, Activity.kind == ActivityKind.planned, Activity.deleted_at.is_(None),
            Activity.placement == Placement.placed, Activity.start_at < end, Activity.end_at > start,
        ).order_by(Activity.start_at)
        return list((await self.session.execute(stmt)).scalars())

    async def slice_invariant_violations(self) -> list[dict]:
        sub = (
            select(ActivityDaySlice.activity_id, func.sum(ActivityDaySlice.minutes).label("sliced"))
            .where(ActivityDaySlice.user_id == self.user_id).group_by(ActivityDaySlice.activity_id).subquery()
        )
        stmt = (
            select(Activity.id, Activity.duration_minutes, func.coalesce(sub.c.sliced, 0))
            .outerjoin(sub, sub.c.activity_id == Activity.id)
            .where(
                Activity.user_id == self.user_id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual,
                Activity.deleted_at.is_(None), Activity.duration_minutes != func.coalesce(sub.c.sliced, 0),
            )
        )
        return [{"activity_id": str(i), "duration": d, "sliced": int(s)} for i, d, s in (await self.session.execute(stmt)).all()]
