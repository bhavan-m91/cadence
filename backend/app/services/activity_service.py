"""Activities: create, edit, delete/restore, split, merge, duplicate, bulk, planned -> actual (FR-058..FR-075)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rolls_back_on_error
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.time import ensure_utc, floor_minute, get_zone, local_date_of
from app.models import Activity, ActivityTag, Category, Project, Tag, Task, User
from app.models.enums import (
    ActivityEventType,
    ActivityKind,
    ActivityOrigin,
    ActivityStatus,
    EventActor,
    Placement,
    TagSource,
)
from app.repositories.activities import ActivitiesRepository, ActivityFilters
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.activity import (
    ActivityCreate,
    ActivityDetail,
    ActivityOut,
    ActivityPatch,
    AlsoTagged,
    BulkIn,
    MergeIn,
    SourceContext,
)
from app.services import serializers, slice_service
from app.services.task_service import task_out

RESTORE_WINDOW = timedelta(days=30)
MIN_SPLIT_MINUTES = 5


class ActivityService:
    def __init__(self, session: AsyncSession, user: User):
        self.session = session
        self.user = user
        self.repo = ActivitiesRepository(session, user.id)
        self.tax = TaxonomyRepository(session, user.id)

    # ------------------------------------------------------------------ helpers
    async def _prefs(self):
        return await UsersRepository(self.session).preferences(self.user.id)

    async def _category(self, category_id: uuid.UUID) -> Category:
        cat = await self.tax.category(category_id)
        if cat is None:
            raise ValidationFailed("Unknown category", path="category_id", rule="not_found")
        if cat.archived_at is not None:
            raise ValidationFailed("Category is archived", path="category_id", rule="archived", code="CATEGORY_ARCHIVED")
        return cat

    async def _tags(self, tag_ids: list[uuid.UUID]) -> list[Tag]:
        ids = list(dict.fromkeys(tag_ids))
        tags = await self.tax.get_many(Tag, ids)
        if len(tags) != len(ids):
            raise ValidationFailed("Unknown tag", path="tag_ids", rule="not_found")
        if any(t.archived_at is not None for t in tags):
            raise ValidationFailed("Archived tags cannot be applied", path="tag_ids", rule="archived", code="TAG_ARCHIVED")
        return tags

    async def _task(self, task_id: uuid.UUID) -> Task:
        task = await self.tax.get(Task, task_id)
        if task is None:
            raise ValidationFailed("Unknown task", path="task_id", rule="not_found")
        return task

    async def _project(self, project_id: uuid.UUID) -> Project:
        proj = await self.tax.get(Project, project_id)
        if proj is None:
            raise ValidationFailed("Unknown project", path="project_id", rule="not_found")
        return proj

    async def _get(self, activity_id: uuid.UUID, *, for_update: bool = False) -> Activity:
        a = await self.repo.get(Activity, activity_id, for_update=for_update)
        if a is None:
            raise NotFound("Activity not found")
        return a

    async def _guard_overlap(self, a_start, a_end, exclude: list[uuid.UUID] | None = None) -> None:
        conflicts = await self.repo.find_overlaps(a_start, a_end, exclude)
        if conflicts:
            raise self._overlap_error(a_start, a_end, conflicts)

    @staticmethod
    def _overlap_error(start, end, conflicts: list[Activity]) -> AppError:
        details = [
            {"id": str(c.id), "title": c.title,
             "overlap_minutes": int((min(end, c.end_at) - max(start, c.start_at)).total_seconds() // 60)}
            for c in conflicts
        ]
        return Conflict("Overlaps another activity", code="ACTIVITY_OVERLAP", details={"conflicts": details})

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            if "activities_no_overlap" in str(e.orig):
                raise Conflict("Overlaps another activity", code="ACTIVITY_OVERLAP", details={"conflicts": []}) from e
            raise

    async def _commit(self) -> None:
        await UsersRepository(self.session).bump_revision(self.user.id)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if "activities_no_overlap" in str(e.orig):
                raise Conflict("Overlaps another activity", code="ACTIVITY_OVERLAP", details={"conflicts": []}) from e
            raise

    def _normalize_times(self, tz_name: str, *, start_at, end_at, duration_minutes, window_start_at, window_end_at) -> dict:
        tz = get_zone(tz_name)
        if start_at is not None and end_at is not None:
            start = floor_minute(ensure_utc(start_at, tz))
            end = floor_minute(ensure_utc(end_at, tz))
            if end <= start:
                raise ValidationFailed("End must be after start", path="end_at", rule="end_before_start")
            if end - start > timedelta(hours=24):
                raise ValidationFailed("An activity cannot be longer than 24 hours", path="end_at", rule="too_long", code="DURATION_TOO_LONG")
            return dict(placement=Placement.placed, start_at=start, end_at=end, window_start_at=None, window_end_at=None,
                        duration_minutes=int((end - start).total_seconds() // 60), local_date=local_date_of(start, tz))
        w_start = floor_minute(ensure_utc(window_start_at, tz))
        w_end = floor_minute(ensure_utc(window_end_at, tz))
        if w_end <= w_start:
            raise ValidationFailed("Window end must be after window start", path="window_end_at", rule="end_before_start")
        if not duration_minutes or duration_minutes > int((w_end - w_start).total_seconds() // 60):
            raise ValidationFailed("Duration does not fit the window", path="duration_minutes", rule="exceeds_window", code="DURATION_EXCEEDS_WINDOW")
        return dict(placement=Placement.unplaced, start_at=None, end_at=None, window_start_at=w_start, window_end_at=w_end,
                    duration_minutes=duration_minutes, local_date=local_date_of(w_start, tz))

    async def _replace_tags(self, a: Activity, tags: list[Tag], source: TagSource = TagSource.user) -> tuple[list[str], list[str]]:
        existing = {l.tag_id: l for l in await self.repo.tag_links(a.id)}
        wanted = {t.id: t for t in tags}
        removed = [tid for tid in existing if tid not in wanted]
        added = [tid for tid in wanted if tid not in existing]
        for tid in removed:
            await self.session.delete(existing[tid])
        for tid in added:
            self.session.add(ActivityTag(activity_id=a.id, tag_id=tid, user_id=self.user.id, source=source))
        await self.session.flush()
        names = {t.id: t.name for t in tags}
        if removed:
            removed_tags = await self.tax.get_many(Tag, removed)
            names.update({t.id: t.name for t in removed_tags})
        return [names[t] for t in added], [names[t] for t in removed]

    async def _out(self, a: Activity) -> ActivityOut:
        await self.session.refresh(a)
        return (await serializers.activities_out(self.session, self.user.id, [a]))[0]

    # ------------------------------------------------------------------ create
    @rolls_back_on_error
    async def create(self, body: ActivityCreate) -> ActivityOut:
        cat = await self._category(body.category_id)
        tags = await self._tags(body.tag_ids)
        task = await self._task(body.task_id) if body.task_id else None
        project_id = body.project_id
        if project_id:
            await self._project(project_id)
        elif task and task.project_id:
            project_id = task.project_id
        tz_name = body.timezone or self.user.timezone
        times = self._normalize_times(
            tz_name, start_at=body.start_at, end_at=body.end_at, duration_minutes=body.duration_minutes,
            window_start_at=body.window_start_at, window_end_at=body.window_end_at,
        )
        if body.kind == ActivityKind.actual and times["placement"] == Placement.placed:
            await self._guard_overlap(times["start_at"], times["end_at"])
        a = Activity(
            user_id=self.user.id, title=body.title, description=body.description, category_id=cat.id, task_id=body.task_id,
            project_id=project_id, location_type=body.location_type, kind=body.kind, status=ActivityStatus.confirmed,
            time_certainty=body.time_certainty, timezone=tz_name, origin=ActivityOrigin.manual, **times,
        )
        self.session.add(a)
        await self._flush()
        if tags:
            await self._replace_tags(a, tags)
        self.repo.add_event(a.id, ActivityEventType.created, EventActor.user, {"origin": "manual"})
        await slice_service.rebuild(self.session, a)
        await self._commit()
        return await self._out(a)

    # ------------------------------------------------------------------ read
    async def detail(self, activity_id: uuid.UUID) -> ActivityDetail:
        a = await self._get(activity_id)
        base = await self._out(a)
        task = None
        if a.task_id:
            t = await self.tax.get(Task, a.task_id)
            if t:
                task = (await task_out(self.session, self.user, [t]))[0]
        tag_ids = [t.tag_id for t in base.tags]
        week = range_of_week(a.local_date, (await self._prefs()).week_start)
        others = await self.repo.also_tagged(a, tag_ids, *week)
        source = SourceContext(quote=a.source_quote, entry_id=a.journal_entry_id)
        if a.journal_entry_id and a.source_start is not None:
            from app.models import JournalEntry

            entry = await self.session.get(JournalEntry, a.journal_entry_id)
            if entry:
                source.context_before = entry.raw_text[max(0, a.source_start - 120): a.source_start]
                source.context_after = entry.raw_text[a.source_end: (a.source_end or 0) + 120]
        return ActivityDetail(
            **base.model_dump(), task=task, source=source,
            also_tagged=[AlsoTagged(id=o.id, title=o.title, start_at=o.start_at, duration_minutes=o.duration_minutes) for o in others],
        )

    async def search(self, f: ActivityFilters, limit: int, cursor) -> tuple[list[ActivityOut], bool]:
        rows = await self.repo.search(f, limit, cursor)
        has_more = len(rows) > limit
        return await serializers.activities_out(self.session, self.user.id, rows[:limit]), has_more

    async def events(self, activity_id: uuid.UUID):
        await self._get(activity_id)
        return await self.repo.events(activity_id)

    # ------------------------------------------------------------------ edit
    @rolls_back_on_error
    async def patch(self, activity_id: uuid.UUID, body: ActivityPatch) -> ActivityOut:
        a = await self._get(activity_id, for_update=True)
        if a.version != body.version:
            raise Conflict("This activity was changed elsewhere", code="VERSION_CONFLICT", details={"current_version": a.version})
        changes: dict[str, list] = {}
        fields = body.model_fields_set

        def set_(name: str, new):
            old = getattr(a, name)
            if old != new:
                changes[name] = [_jsonable(old), _jsonable(new)]
                setattr(a, name, new)

        if body.title is not None:
            set_("title", body.title)
        if "description" in fields and body.description is not None:
            set_("description", body.description)
        if body.category_id is not None and body.category_id != a.category_id:
            set_("category_id", (await self._category(body.category_id)).id)
        if body.location_type is not None:
            set_("location_type", body.location_type)
        if body.time_certainty is not None:
            set_("time_certainty", body.time_certainty)
        for name in body.clear:
            if name == "task_id":
                set_("task_id", None)
            elif name in ("project_id", "location_type", "description"):
                set_(name, None)

        task_changed = False
        if body.task_id is not None and body.task_id != a.task_id:
            old_task = await self.tax.get(Task, a.task_id) if a.task_id else None
            new_task = await self._task(body.task_id)
            inherited = a.project_id is not None and (old_task is None or a.project_id == old_task.project_id)
            set_("task_id", new_task.id)
            task_changed = True
            if inherited or a.project_id is None:
                set_("project_id", new_task.project_id)
        if body.project_id is not None and body.project_id != a.project_id:
            set_("project_id", (await self._project(body.project_id)).id)
        if "task_id" in body.clear:
            task_changed = True

        time_touched = any(f in fields for f in ("start_at", "end_at", "duration_minutes", "window_start_at", "window_end_at"))
        if time_touched:
            self._apply_time_patch(a, body, set_)
            if a.kind == ActivityKind.actual and a.placement == Placement.placed:
                await self._guard_overlap(a.start_at, a.end_at, [a.id])

        if not changes:
            return await self._out(a)
        a.user_edited = True
        a.version += 1
        await self._flush()
        self.repo.add_event(a.id, ActivityEventType.task_linked if task_changed and len(changes) <= 2 and "task_id" in changes else ActivityEventType.edited,
                            EventActor.user, {"changes": changes})
        await slice_service.rebuild(self.session, a)
        await self._commit()
        return await self._out(a)

    def _apply_time_patch(self, a: Activity, body: ActivityPatch, set_) -> None:
        tz_name = a.timezone
        start = body.start_at if body.start_at is not None else a.start_at
        end = body.end_at if body.end_at is not None else a.end_at
        if a.placement == Placement.placed or (body.start_at is not None and body.end_at is not None):
            if body.duration_minutes is not None and body.end_at is None and start is not None:
                end = ensure_utc(start, get_zone(tz_name)) + timedelta(minutes=body.duration_minutes)
            if start is None or end is None:
                raise ValidationFailed("start_at and end_at are required", path="start_at", rule="required")
            times = self._normalize_times(tz_name, start_at=start, end_at=end, duration_minutes=None, window_start_at=None, window_end_at=None)
        else:
            times = self._normalize_times(
                tz_name, start_at=None, end_at=None,
                duration_minutes=body.duration_minutes if body.duration_minutes is not None else a.duration_minutes,
                window_start_at=body.window_start_at or a.window_start_at, window_end_at=body.window_end_at or a.window_end_at,
            )
        for k, v in times.items():
            set_(k, v)

    # ------------------------------------------------------------------ delete / restore
    @rolls_back_on_error
    async def delete(self, activity_id: uuid.UUID) -> None:
        a = await self._get(activity_id, for_update=True)
        await self._soft_delete(a)
        await self._commit()

    async def _soft_delete(self, a: Activity) -> None:
        a.deleted_at = datetime.now(UTC)
        a.version += 1
        await self.session.flush()
        self.repo.add_event(a.id, ActivityEventType.deleted, EventActor.user)
        await slice_service.rebuild(self.session, a)

    @rolls_back_on_error
    async def restore(self, activity_id: uuid.UUID) -> ActivityOut:
        a = await self.repo.get_deleted(activity_id)
        if a is None or datetime.now(UTC) - a.deleted_at > RESTORE_WINDOW:
            raise NotFound("Activity not found")
        if a.kind == ActivityKind.actual and a.placement == Placement.placed and a.status == ActivityStatus.confirmed:
            await self._guard_overlap(a.start_at, a.end_at, [a.id])
        a.deleted_at = None
        a.version += 1
        await self._flush()
        self.repo.add_event(a.id, ActivityEventType.restored, EventActor.user)
        await slice_service.rebuild(self.session, a)
        await self._commit()
        return await self._out(a)

    # ------------------------------------------------------------------ tags
    @rolls_back_on_error
    async def set_tags(self, activity_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> ActivityOut:
        a = await self._get(activity_id, for_update=True)
        tags = await self._tags(tag_ids)
        added, removed = await self._replace_tags(a, tags)
        if added:
            self.repo.add_event(a.id, ActivityEventType.tagged, EventActor.user, {"tags": added})
        if removed:
            self.repo.add_event(a.id, ActivityEventType.untagged, EventActor.user, {"tags": removed})
        if added or removed:
            a.user_edited = True
            a.version += 1
        await self._commit()
        return await self._out(a)

    # ------------------------------------------------------------------ split
    @rolls_back_on_error
    async def split(self, activity_id: uuid.UUID, at: datetime) -> tuple[ActivityOut, ActivityOut]:
        a = await self._get(activity_id, for_update=True)
        if a.placement != Placement.placed:
            raise AppError("Only placed activities can be split", code="SPLIT_POINT_INVALID", status=422)
        at = floor_minute(ensure_utc(at, get_zone(a.timezone)))
        min_gap = timedelta(minutes=MIN_SPLIT_MINUTES)
        if at - a.start_at < min_gap or a.end_at - at < min_gap:
            raise AppError("Each part must be at least 5 minutes", code="SPLIT_POINT_INVALID", status=422)
        old_end = a.end_at
        links = await self.repo.tag_links(a.id)
        a.end_at = at
        a.duration_minutes = int((at - a.start_at).total_seconds() // 60)
        a.user_edited = True
        a.version += 1
        await self._flush()
        b = Activity(
            user_id=self.user.id, title=a.title, description=a.description, category_id=a.category_id, task_id=a.task_id,
            project_id=a.project_id, location_type=a.location_type, kind=a.kind, status=a.status, placement=Placement.placed,
            start_at=at, end_at=old_end, duration_minutes=int((old_end - at).total_seconds() // 60), time_certainty=a.time_certainty,
            timezone=a.timezone, local_date=local_date_of(at, get_zone(a.timezone)), origin=ActivityOrigin.split,
            derived_from_id=a.id, journal_entry_id=a.journal_entry_id, user_edited=True,
        )
        self.session.add(b)
        await self._flush()
        for l in links:
            self.session.add(ActivityTag(activity_id=b.id, tag_id=l.tag_id, user_id=self.user.id, source=l.source, confidence=l.confidence, reason=l.reason))
        self.repo.add_event(a.id, ActivityEventType.split, EventActor.user, {"at": at.isoformat(), "created": str(b.id)})
        self.repo.add_event(b.id, ActivityEventType.split, EventActor.user, {"from": str(a.id)})
        await slice_service.rebuild(self.session, a)
        await slice_service.rebuild(self.session, b)
        await self._commit()
        return await self._out(a), await self._out(b)

    # ------------------------------------------------------------------ merge
    @rolls_back_on_error
    async def merge(self, body: MergeIn) -> ActivityOut:
        ids = list(dict.fromkeys(body.activity_ids))
        rows = await self.repo.get_many(Activity, ids)
        if len(rows) != len(ids):
            raise NotFound("Activity not found")
        for r in rows:  # lock in a stable order
            await self._get(r.id, for_update=True)
        prefs = await self._prefs()
        kinds = {(r.kind, r.status) for r in rows}
        if len(kinds) != 1:
            raise AppError("Only activities of the same kind can be merged", code="MERGE_INVALID", status=422)
        placements = {r.placement for r in rows}
        if len(placements) != 1:
            raise AppError("Activities must be all placed or all unplaced", code="MERGE_NOT_CONTIGUOUS", status=422)
        categories = {r.category_id for r in rows}
        if body.category_id:
            category_id = (await self._category(body.category_id)).id
        elif len(categories) == 1:
            category_id = rows[0].category_id
        else:
            raise AppError("Choose a category for the merged activity", code="CATEGORY_REQUIRED", status=422)

        placed = rows[0].placement == Placement.placed
        rows.sort(key=lambda r: r.start_at if placed else r.window_start_at)
        survivor, others = rows[0], rows[1:]
        if placed:
            for prev, nxt in zip(rows, rows[1:], strict=False):
                gap = nxt.start_at - prev.end_at
                if gap < timedelta(0) or gap > timedelta(minutes=prefs.gap_min_minutes):
                    raise AppError("Activities must be contiguous to merge", code="MERGE_NOT_CONTIGUOUS", status=422)
        all_links = {}
        for r in rows:
            for l in await self.repo.tag_links(r.id):
                all_links.setdefault(l.tag_id, l)
        for o in others:
            o.merged_into_id = survivor.id
            await self._soft_delete(o)
            self.repo.add_event(o.id, ActivityEventType.merged, EventActor.user, {"into": str(survivor.id)})
        await self.session.flush()
        if placed:
            survivor.end_at = rows[-1].end_at
            survivor.duration_minutes = int((survivor.end_at - survivor.start_at).total_seconds() // 60)
        else:
            survivor.window_start_at = min(r.window_start_at for r in rows)
            survivor.window_end_at = max(r.window_end_at for r in rows)
            survivor.duration_minutes = min(1440, sum(r.duration_minutes for r in rows))
        survivor.category_id = category_id
        if body.title:
            survivor.title = body.title
        survivor.origin = ActivityOrigin.merge
        survivor.user_edited = True
        survivor.version += 1
        await self._flush()
        existing = {l.tag_id for l in await self.repo.tag_links(survivor.id)}
        for tid, l in all_links.items():
            if tid not in existing:
                self.session.add(ActivityTag(activity_id=survivor.id, tag_id=tid, user_id=self.user.id, source=l.source, confidence=l.confidence, reason=l.reason))
        self.repo.add_event(survivor.id, ActivityEventType.merged, EventActor.user, {"merged": [str(o.id) for o in others]})
        await slice_service.rebuild(self.session, survivor)
        await self._commit()
        return await self._out(survivor)

    # ------------------------------------------------------------------ duplicate
    @rolls_back_on_error
    async def duplicate(self, activity_id: uuid.UUID, start_at: datetime | None) -> ActivityOut:
        src = await self._get(activity_id)
        links = await self.repo.tag_links(src.id)
        fields = dict(
            user_id=self.user.id, title=src.title, description=src.description, category_id=src.category_id, task_id=src.task_id,
            project_id=src.project_id, location_type=src.location_type, kind=src.kind, status=src.status,
            time_certainty=src.time_certainty, timezone=src.timezone, origin=ActivityOrigin.duplicate, derived_from_id=src.id,
            user_edited=True,
        )
        tz = get_zone(src.timezone)
        if src.placement == Placement.placed:
            start = floor_minute(ensure_utc(start_at, tz)) if start_at else src.end_at
            end = start + timedelta(minutes=src.duration_minutes)
            if src.kind == ActivityKind.actual:
                await self._guard_overlap(start, end)
            fields.update(placement=Placement.placed, start_at=start, end_at=end, duration_minutes=src.duration_minutes, local_date=local_date_of(start, tz))
        else:
            fields.update(placement=Placement.unplaced, window_start_at=src.window_start_at, window_end_at=src.window_end_at,
                          duration_minutes=src.duration_minutes, local_date=src.local_date)
        dup = Activity(**fields)
        self.session.add(dup)
        await self._flush()
        for l in links:
            self.session.add(ActivityTag(activity_id=dup.id, tag_id=l.tag_id, user_id=self.user.id, source=l.source, confidence=l.confidence, reason=l.reason))
        self.repo.add_event(dup.id, ActivityEventType.duplicated, EventActor.user, {"from": str(src.id)})
        await slice_service.rebuild(self.session, dup)
        await self._commit()
        return await self._out(dup)

    # ------------------------------------------------------------------ planned -> actual
    @rolls_back_on_error
    async def mark_done(self, activity_id: uuid.UUID, start_at: datetime | None, end_at: datetime | None) -> ActivityOut:
        a = await self._get(activity_id, for_update=True)
        if a.kind != ActivityKind.planned:
            raise AppError("Only planned activities can be marked done", code="NOT_PLANNED", status=422)
        if (start_at is None) != (end_at is None):
            raise ValidationFailed("start_at and end_at must be sent together", path="start_at", rule="together")
        if start_at is not None:
            for k, v in self._normalize_times(a.timezone, start_at=start_at, end_at=end_at, duration_minutes=None, window_start_at=None, window_end_at=None).items():
                setattr(a, k, v)
        if a.placement == Placement.placed:
            await self._guard_overlap(a.start_at, a.end_at, [a.id])
        a.kind = ActivityKind.actual
        a.user_edited = True
        a.version += 1
        await self._flush()
        self.repo.add_event(a.id, ActivityEventType.edited, EventActor.user, {"changes": {"kind": ["planned", "actual"]}})
        await slice_service.rebuild(self.session, a)
        await self._commit()
        return await self._out(a)

    # ------------------------------------------------------------------ bulk
    @rolls_back_on_error
    async def bulk(self, body: BulkIn) -> int:
        ids = list(dict.fromkeys(body.ids))
        rows = await self.repo.get_many(Activity, ids)
        if len(rows) != len(ids):
            raise NotFound("Activity not found")
        value = body.value
        if body.op in ("add_tags", "remove_tags"):
            if not isinstance(value, list):
                raise ValidationFailed("value must be a list of tag ids", path="value", rule="list_required")
            tags = await self._tags(value) if body.op == "add_tags" else await self.tax.get_many(Tag, value)
            for a in rows:
                current = {l.tag_id: l for l in await self.repo.tag_links(a.id)}
                if body.op == "add_tags":
                    for t in tags:
                        if t.id not in current:
                            self.session.add(ActivityTag(activity_id=a.id, tag_id=t.id, user_id=self.user.id, source=TagSource.user))
                    evt = ActivityEventType.tagged
                else:
                    for t in tags:
                        if t.id in current:
                            await self.session.delete(current[t.id])
                    evt = ActivityEventType.untagged
                self.repo.add_event(a.id, evt, EventActor.user, {"tags": [t.name for t in tags], "bulk": True})
                a.user_edited = True
                a.version += 1
        elif body.op == "set_category":
            if not isinstance(value, uuid.UUID):
                raise ValidationFailed("value must be a category id", path="value", rule="uuid_required")
            cat = await self._category(value)
            for a in rows:
                a.category_id = cat.id
                a.user_edited = True
                a.version += 1
                self.repo.add_event(a.id, ActivityEventType.edited, EventActor.user, {"changes": {"category_id": [None, str(cat.id)]}, "bulk": True})
            await self.session.flush()
            for a in rows:
                await slice_service.rebuild(self.session, a)
        elif body.op in ("set_task", "set_project"):
            if value is not None and not isinstance(value, uuid.UUID):
                raise ValidationFailed("value must be an id or null", path="value", rule="uuid_required")
            if body.op == "set_task":
                task = await self._task(value) if value else None
                for a in rows:
                    a.task_id = value
                    if task and task.project_id:
                        a.project_id = task.project_id
                    a.user_edited = True
                    a.version += 1
                    self.repo.add_event(a.id, ActivityEventType.task_linked, EventActor.user, {"task_id": str(value) if value else None, "bulk": True})
            else:
                if value:
                    await self._project(value)
                for a in rows:
                    a.project_id = value
                    a.user_edited = True
                    a.version += 1
                    self.repo.add_event(a.id, ActivityEventType.edited, EventActor.user, {"changes": {"project_id": [None, str(value) if value else None]}, "bulk": True})
        else:  # delete
            for a in rows:
                await self._soft_delete(a)
        await self.session.flush()
        await self._commit()
        return len(rows)


def range_of_week(d, week_start: int):
    from app.core.time import week_start_date

    start = week_start_date(d, week_start)
    return start, start + timedelta(days=6)


def _jsonable(v):
    if isinstance(v, (datetime,)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v
