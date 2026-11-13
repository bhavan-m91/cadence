"""Timeline: per-day blocks, gaps and coverage for a range (FR-067, D-05). Gaps are computed, never stored."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ValidationFailed
from app.core.time import compute_slices, date_range, day_bounds, elapsed_minutes, get_zone
from app.models import Activity, User
from app.repositories.activities import ActivitiesRepository, ActivityFilters
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.timeline import Block, Coverage, DayTimeline, Gap, IdealRow, TimelineOut, UnplacedItem
from app.services import serializers

MAX_DAYS = 14


class TimelineService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = ActivitiesRepository(session, user.id)
        self.tax = TaxonomyRepository(session, user.id)

    async def build(self, from_date: date, to_date: date, filters: ActivityFilters | None, ideal: bool) -> TimelineOut:
        if to_date < from_date:
            raise ValidationFailed("'to' must not be before 'from'", path="to", rule="range")
        if (to_date - from_date).days + 1 > MAX_DAYS:
            raise AppError(f"Timeline ranges are limited to {MAX_DAYS} days", code="RANGE_TOO_LONG", status=422)
        tz = get_zone(self.user.timezone)
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        now = datetime.now(UTC)
        today = now.astimezone(tz).date()

        slice_rows = await self.repo.slices_in_range(from_date, to_date)
        range_start, range_end = day_bounds(from_date, tz)[0], day_bounds(to_date, tz)[1]
        planned_rows = await self.repo.planned_in_range(range_start, range_end)

        activities = {a.id: a for _, a in slice_rows} | {a.id: a for a in planned_rows}
        out_rows = {o.id: o for o in await serializers.activities_out(self.session, self.user.id, list(activities.values()))}
        visible = await self._visible_ids(filters, list(activities)) if filters else None

        placed_by_day: dict[date, list[tuple[datetime, datetime, Activity]]] = defaultdict(list)
        unplaced_by_day: dict[date, list[tuple[int, Activity]]] = defaultdict(list)
        for sl, act in slice_rows:
            if sl.is_placed:
                placed_by_day[sl.local_date].append((sl.slice_start_at, sl.slice_end_at, act))
            else:
                unplaced_by_day[sl.local_date].append((sl.minutes, act))

        days: list[DayTimeline] = []
        for d in date_range(from_date, to_date):
            d_start, d_end = day_bounds(d, tz)
            full = elapsed_minutes(d, tz)
            placed_intervals = sorted((max(s, d_start), min(e, d_end), a) for s, e, a in placed_by_day.get(d, []))
            blocks = [self._block(out_rows[a.id], s, e, d_start, d_end) for s, e, a in placed_intervals
                      if visible is None or a.id in visible]
            planned = []
            for a in planned_rows:
                for sl in compute_slices(a.start_at, a.end_at, tz):
                    if sl.local_date == d and (visible is None or a.id in visible):
                        planned.append(self._block(out_rows[a.id], sl.start, sl.end, d_start, d_end))
            unplaced = [UnplacedItem(id=a.id, title=a.title, minutes=m, category=out_rows[a.id].category,
                                     window_start_at=a.window_start_at, window_end_at=a.window_end_at)
                        for m, a in unplaced_by_day.get(d, []) if visible is None or a.id in visible]

            placed_minutes = sum(int((e - s).total_seconds() // 60) for s, e, _ in placed_intervals)
            unplaced_minutes = sum(m for m, _ in unplaced_by_day.get(d, []))
            logged = placed_minutes + unplaced_minutes
            if d > today:
                elapsed, horizon = 0, d_start
            elif d == today:
                horizon = min(max(now, d_start), d_end)
                elapsed = int((horizon - d_start).total_seconds() // 60)
            else:
                elapsed, horizon = full, d_end
            gaps = self._gaps([(s, e) for s, e, _ in placed_intervals], d_start, horizon, prefs.gap_min_minutes)
            unlogged = max(0, elapsed - logged)
            ended = d < today
            days.append(DayTimeline(
                date=d, day_start_at=d_start, day_end_at=d_end, blocks=blocks, planned=planned, unplaced=unplaced, gaps=gaps,
                coverage=Coverage(placed=placed_minutes, logged=logged, elapsed=elapsed, unlogged=unlogged,
                                  pct=round(min(1.0, logged / elapsed), 4) if elapsed else 1.0,
                                  complete=ended and unlogged <= prefs.coverage_tolerance_minutes),
                ideal=await self._ideal(d) if ideal else None,
            ))
        return TimelineOut(days=days, timezone=self.user.timezone)

    async def _visible_ids(self, f: ActivityFilters, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        from sqlalchemy import select

        stmt = self.repo._apply(select(Activity.id), f).where(Activity.id.in_(ids))
        # Planned rows are filtered on kind elsewhere; allow both kinds through the shared filter
        return {i for (i,) in (await self.session.execute(stmt)).all()}

    @staticmethod
    def _block(o, start: datetime, end: datetime, d_start: datetime, d_end: datetime) -> Block:
        s, e = max(start, d_start), min(end, d_end)
        return Block(
            id=o.id, version=o.version, title=o.title, kind=o.kind, start_at=s, end_at=e, minutes=int((e - s).total_seconds() // 60), category=o.category,
            tags=o.tags, time_certainty=o.time_certainty, needs_review=o.needs_review, flags=o.flags,
            continues_from_previous_day=o.start_at is not None and o.start_at < d_start,
            continues_to_next_day=o.end_at is not None and o.end_at > d_end, location_type=o.location_type,
        )

    @staticmethod
    def _gaps(intervals: list[tuple[datetime, datetime]], start: datetime, horizon: datetime, min_minutes: int) -> list[Gap]:
        gaps: list[Gap] = []
        cursor = start
        for s, e in intervals:
            if s > cursor:
                gaps.append((cursor, min(s, horizon)))
            cursor = max(cursor, e)
        if cursor < horizon:
            gaps.append((cursor, horizon))
        return [Gap(start_at=a, end_at=b, minutes=int((b - a).total_seconds() // 60))
                for a, b in gaps if b > a and int((b - a).total_seconds() // 60) >= min_minutes]

    async def _ideal(self, d: date) -> list[IdealRow]:
        allocations = await self.tax.ideal_day_allocations(d)
        if not allocations:
            return []
        from app.models import Category

        cats = {c.id: c for c in await self.tax.get_many(Category, [a.category_id for a in allocations])}
        return [IdealRow(category_id=a.category_id, name=cats[a.category_id].name, color=cats[a.category_id].color, minutes=a.minutes)
                for a in allocations if a.category_id in cats]
