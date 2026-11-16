"""Dashboard numbers (M8). One metric vocabulary, one source (`activity_day_slices`), no model involved.

Dates are local dates in each activity's own timezone (slices already carry them). Today is provisional; drafts and plans never count.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import insights, sleep
from app.analytics.metrics import adherence as adherence_of
from app.analytics.metrics import coverage as coverage_of
from app.analytics.metrics import pace_expected, pct_change, prorate, row_status
from app.core import clock
from app.core.errors import AppError, ValidationFailed
from app.core.time import date_range, day_bounds, elapsed_minutes, get_zone, week_start_date
from app.models import Activity, IdealAllocation, User
from app.models.enums import IdealKind, RootKind, TimeCertainty
from app.repositories.activities import ActivitiesRepository, ActivityFilters
from app.repositories.analytics_queries import AnalyticsQueries, SliceRow
from app.repositories.ideal import IdealRepository
from app.repositories.journal import JournalRepository
from app.repositories.tasks import TasksRepository
from app.repositories.users import UsersRepository
from app.schemas.analytics import (
    AdherenceOut,
    BannerOut,
    BreakdownItem,
    BreakdownOut,
    CategoryTotal,
    CertaintyOut,
    CoverageOut,
    DayAnalytics,
    DayColumn,
    DeadlineOut,
    FocusBlock,
    FocusDay,
    IdealCompare,
    IdealCompareRow,
    Kpis,
    OverviewOut,
    ProjectTotal,
    SleepBlock,
    SleepNight,
    Streaks,
    TagTotal,
    TaskTotal,
    TrendPoint,
    TrendsOut,
    WeekAnalytics,
    WorkPersonal,
)
from app.services.tag_service import goal_status
from app.services.timeline_service import TimelineService

ROOT_ORDER = {"work": 0, "personal": 1, "sleep": 2}
LENS_ROOTS: dict[str, set[RootKind] | None] = {"all": None, "work": {RootKind.work}, "personal": {RootKind.personal, RootKind.sleep}}
NEUTRAL = "#5E6582"
MAX_TREND_PERIODS = {"day": 366, "week": 52}


@dataclass
class Agg:
    by_cat: dict[uuid.UUID, int] = field(default_factory=lambda: defaultdict(int))
    by_tag: dict[uuid.UUID, int] = field(default_factory=lambda: defaultdict(int))
    by_task: dict[uuid.UUID, int] = field(default_factory=lambda: defaultdict(int))
    by_project: dict[uuid.UUID, int] = field(default_factory=lambda: defaultdict(int))
    by_day_cat: dict[date, dict[uuid.UUID, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    placed: dict[date, int] = field(default_factory=lambda: defaultdict(int))
    unplaced: dict[date, int] = field(default_factory=lambda: defaultdict(int))
    focus: dict[date, int] = field(default_factory=lambda: defaultdict(int))
    recorded: int = 0
    estimated: int = 0
    work: int = 0
    personal: int = 0
    work_outside: int = 0
    work_outside_hours: int = 0
    personal_office: int = 0


@dataclass
class Period:
    scope: str
    dates: list[date]
    coverage: CoverageOut
    certainty: CertaintyOut
    by_category: list[CategoryTotal]
    by_tag: list[TagTotal]
    by_task: list[TaskTotal]
    by_project: list[ProjectTotal]
    work_vs_personal: WorkPersonal
    days: list[DayColumn]
    sleep: SleepBlock
    focus: FocusBlock
    ideal: IdealCompare | None
    setup_needed: bool
    prev: dict[str, float | int | None] = field(default_factory=dict)


class AnalyticsService:
    def __init__(self, session: AsyncSession, user: User, lens: str | None = None):
        self.session, self.user = session, user
        # The Work / Personal lens narrows every total to one side of life. Coverage stays whole-day: a gap is a gap whichever side you look at.
        self.roots: set[RootKind] | None = LENS_ROOTS.get(lens or "all")
        self.tz: ZoneInfo = get_zone(user.timezone)
        self.q = AnalyticsQueries(session, user.id)
        self.ideal = IdealRepository(session, user.id)
        self._prefs = None
        self._cats = None
        self._tags = None
        self.now: datetime = clock.now()
        self.today: date = self.now.astimezone(self.tz).date()

    # ------------------------------------------------------------------ shared context
    async def prefs(self):
        if self._prefs is None:
            self._prefs = await UsersRepository(self.session).preferences(self.user.id)
        return self._prefs

    async def cats(self):
        if self._cats is None:
            self._cats = await self.q.categories()
        return self._cats

    async def tags(self):
        if self._tags is None:
            self._tags = await self.q.tags()
        return self._tags

    def touches_today(self, from_date: date, to_date: date) -> bool:
        return from_date <= self.today <= to_date

    def elapsed(self, d: date) -> int:
        """Minutes of `d` that have happened: all of a past day, none of a future day, part of today."""
        if d > self.today:
            return 0
        if d < self.today:
            return elapsed_minutes(d, self.tz)
        start, end = day_bounds(d, self.tz)
        return int((min(max(self.now, start), end) - start).total_seconds() // 60)

    def in_lens(self, c) -> bool:
        return self.roots is None or (c is not None and c.root_kind in self.roots)

    @property
    def sleep_in_lens(self) -> bool:
        return self.roots is None or RootKind.sleep in self.roots

    # ------------------------------------------------------------------ aggregation
    async def _aggregate(self, rows: list[SliceRow], tag_map: dict[uuid.UUID, list[uuid.UUID]]) -> Agg:
        cats, prefs = await self.cats(), await self.prefs()
        a = Agg()
        for r in rows:
            m, c = r.minutes, cats.get(r.category_id)
            (a.placed if r.is_placed else a.unplaced)[r.local_date] += m
            if not self.in_lens(c):
                continue
            a.by_cat[r.category_id] += m
            a.by_day_cat[r.local_date][r.category_id] += m
            if r.task_id:
                a.by_task[r.task_id] += m
            if r.project_id:
                a.by_project[r.project_id] += m
            for tid in tag_map.get(r.activity_id, []):
                a.by_tag[tid] += m
            if r.certainty == TimeCertainty.stated.value:
                a.recorded += m
            else:
                a.estimated += m
            if c is None:
                continue
            if c.counts_as_focus:
                a.focus[r.local_date] += m
            in_office = self._office_overlap(r, prefs.office_start_minute, prefs.office_end_minute) if r.is_placed and r.start_at and r.end_at else None
            if c.root_kind == RootKind.work:
                a.work += m
                if r.location and r.location != "office":
                    a.work_outside += m
                if in_office is not None:  # time of day, not place: work at 12am-2am happened in personal time
                    a.work_outside_hours += m - in_office
            elif c.root_kind == RootKind.personal:
                a.personal += m
                if in_office:
                    a.personal_office += in_office
        return a

    def _office_overlap(self, r: SliceRow, start_min: int, end_min: int) -> int:
        """Minutes of this slice inside office hours. Office hours apply on weekdays only: a Saturday has none."""
        if r.local_date.isoweekday() > 5 or r.start_at is None or r.end_at is None:
            return 0
        d0 = day_bounds(r.local_date, self.tz)[0]
        lo, hi = d0 + timedelta(minutes=start_min), d0 + timedelta(minutes=end_min)
        return max(0, int((min(r.end_at, hi) - max(r.start_at, lo)).total_seconds() // 60))

    def _coverage(self, dates: list[date], a: Agg, tolerance: int) -> tuple[CoverageOut, list[DayColumn]]:
        cols: list[DayColumn] = []
        for d in dates:
            el = self.elapsed(d)
            placed, unplaced = a.placed.get(d, 0), a.unplaced.get(d, 0)
            logged = placed + unplaced
            unlogged = max(0, el - logged)
            cols.append(DayColumn(date=d, placed=placed, unplaced=unplaced, logged=logged, elapsed=el, unlogged=unlogged,
                                  complete=d < self.today and unlogged <= tolerance, focus=a.focus.get(d, 0), sleep=0))
        placed, unplaced = sum(c.placed for c in cols), sum(c.unplaced for c in cols)
        el = sum(c.elapsed for c in cols)
        logged = placed + unplaced
        cov = CoverageOut(placed=placed, unplaced=unplaced, logged=logged, elapsed=el, unlogged=max(0, el - logged), pct=coverage_of(logged, el),
                          complete=all(c.complete for c in cols))
        return cov, cols

    # ------------------------------------------------------------------ Ideal comparison (FR-126, FR-127)
    async def _templates(self, kind: IdealKind) -> list[tuple[date, list[IdealAllocation]]]:
        out = []
        for t in await self.ideal.versions(kind):  # newest first
            out.append((t.effective_from, await self.ideal.allocations(t.id)))
        return out

    @staticmethod
    def _in_force(versions: list[tuple[date, list[IdealAllocation]]], on: date):
        return next(((eff, al) for eff, al in versions if eff <= on), None)

    async def _compare(self, kind: IdealKind, dates: list[date], by_day: dict[date, dict[uuid.UUID, int]],
                       tpl: tuple[date, list[IdealAllocation]] | None) -> IdealCompare | None:
        if tpl is None:
            return None
        eff, allocs = tpl
        cats = await self.cats()
        allocs = [al for al in allocs if self.in_lens(cats.get(al.category_id))]
        if not allocs:
            return None
        allocated = {a.category_id for a in allocs}
        day = kind == IdealKind.day
        completed = [d for d in dates if d < self.today]
        as_of = completed[-1] if completed else None
        counted = dates if day else completed
        actual: dict[uuid.UUID, int] = {a.category_id: 0 for a in allocs}
        other = 0
        for d in counted:
            for cid, m in by_day.get(d, {}).items():
                owner = next((x for x in (cats[cid].path_ids if cid in cats else []) if x in allocated), None)
                if owner is None:
                    other += m
                else:
                    actual[owner] += m
        rows: list[IdealCompareRow] = []
        pairs: list[tuple[int, int]] = []
        for al in allocs:
            c = cats[al.category_id]
            if day:
                d = dates[0]
                expected = al.minutes if d < self.today else prorate(al.minutes, self.elapsed(d), elapsed_minutes(d, self.tz)) if d == self.today else 0
            else:
                expected = pace_expected(al.minutes, al.distribution, dates, as_of) if as_of else 0
            delta = actual[al.category_id] - expected
            rows.append(IdealCompareRow(category_id=c.id, name=c.name, path_names=c.path_names, color=c.color, root_kind=c.root_kind.value,
                                        distribution=al.distribution if not day else None, target=al.minutes, expected=expected,
                                        actual=actual[al.category_id], delta=delta, status=row_status(delta, al.minutes)))
            if c.root_kind != RootKind.sleep:
                pairs.append((actual[al.category_id], expected))
        rows.sort(key=lambda r: (ROOT_ORDER[r.root_kind], r.path_names))
        value = adherence_of(pairs)
        return IdealCompare(kind=kind.value, effective_from=eff, rows=rows, unallocated_actual=other,
                            adherence=AdherenceOut(value=value, provisional=day and dates[0] == self.today))

    # ------------------------------------------------------------------ one period (a day or a week)
    async def _period(self, scope: str, dates: list[date], with_prev: bool = True) -> Period:
        prefs, cats, tags = await self.prefs(), await self.cats(), await self.tags()
        lo, hi = dates[0], dates[-1]
        rows = await self.q.slices(lo, hi)
        a = await self._aggregate(rows, await self.q.tags_by_activity(lo, hi))
        coverage, cols = self._coverage(dates, a, prefs.coverage_tolerance_minutes)

        waking = sum(m for cid, m in a.by_cat.items() if cid in cats and cats[cid].root_kind != RootKind.sleep)
        by_category = sorted((CategoryTotal(category_id=cid, name=cats[cid].name, path_names=cats[cid].path_names, color=cats[cid].color,
                                            root_kind=cats[cid].root_kind.value, minutes=m,
                                            share=round(m / waking, 4) if waking and cats[cid].root_kind != RootKind.sleep else 0.0)
                              for cid, m in a.by_cat.items() if cid in cats), key=lambda c: -c.minutes)
        by_tag = sorted((TagTotal(tag_id=tid, name=tags[tid].name, color=tags[tid].color, minutes=m, share=round(m / waking, 4) if waking else 0.0,
                                  goal_kind=tags[tid].goal_kind.value, goal_weekly_minutes=tags[tid].goal_weekly_minutes,
                                  goal_status=goal_status(tags[tid], m) if scope == "week" else "none")
                         for tid, m in a.by_tag.items() if tid in tags), key=lambda t: -t.minutes)
        task_rows = await self.q.tasks(list(a.by_task))
        by_task = sorted((TaskTotal(task_id=tid, title=task_rows[tid].title, project_id=task_rows[tid].project_id, minutes=m)
                          for tid, m in a.by_task.items() if tid in task_rows), key=lambda t: -t.minutes)
        proj_rows = await self.q.projects(list(a.by_project))
        by_project = sorted((ProjectTotal(project_id=pid, name=proj_rows[pid].name, minutes=m) for pid, m in a.by_project.items() if pid in proj_rows),
                            key=lambda p: -p.minutes)

        kind = IdealKind.day if scope == "day" else IdealKind.week
        day_versions = await self._templates(IdealKind.day)
        day_tpl = self._in_force(day_versions, lo)
        tpl = day_tpl if scope == "day" else self._in_force(await self._templates(IdealKind.week), lo)
        ideal = await self._compare(kind, dates, a.by_day_cat, tpl)

        # sleep: nights by wake date. A day reads the 7 nights ending that day, a week reads its own 7.
        n_dates = date_range(lo - timedelta(days=6), hi) if scope == "day" else dates
        nights = sleep.attribute(await self.q.sleep_activities(n_dates[0], n_dates[-1], self.tz), self.tz) if self.sleep_in_lens else {}
        stats = sleep.summarize(nights, n_dates, self.tz, prefs.short_night_minutes)
        sleep_target = sum(al.minutes for al in (day_tpl[1] if day_tpl else []) if al.category_id in cats and cats[al.category_id].root_kind == RootKind.sleep) or None
        sleep_target = sleep_target if self.sleep_in_lens else None
        for c in cols:
            c.sleep = nights[c.date].minutes if c.date in nights else 0
        sleep_block = SleepBlock(
            nights=[SleepNight(date=d, minutes=nights[d].minutes, bed_at=nights[d].bed_at, wake_at=nights[d].wake_at, short=nights[d].minutes < prefs.short_night_minutes)
                    for d in n_dates if d in nights], target=sleep_target, **stats)

        focus_alloc = sum(al.minutes for al in (tpl[1] if tpl else []) if al.category_id in cats and cats[al.category_id].counts_as_focus and self.in_lens(cats[al.category_id])) or None
        focus = FocusBlock(days=[FocusDay(date=d, minutes=a.focus.get(d, 0)) for d in dates], minutes=sum(a.focus.get(d, 0) for d in dates), target=focus_alloc)

        p = Period(scope, dates, coverage, CertaintyOut(recorded=a.recorded, estimated=a.estimated), by_category, by_tag, by_task, by_project,
                   WorkPersonal(work=a.work, personal=a.personal, work_outside_office=a.work_outside, work_outside_hours=a.work_outside_hours, personal_in_office_hours=a.personal_office),
                   cols, sleep_block, focus, ideal, ideal is None)
        if with_prev:
            n = len(dates)
            prev = await self._period(scope, [d - timedelta(days=n) for d in dates], with_prev=False)
            p.prev = {"adherence": prev.ideal.adherence.value if prev.ideal else None, "coverage_pct": prev.coverage.pct, "logged": prev.coverage.logged,
                      "focus": prev.focus.minutes, "sleep_avg": prev.sleep.avg_minutes}
            if p.ideal:
                p.ideal.adherence.vs_prev = pct_change(p.ideal.adherence.value, p.prev["adherence"])
        return p

    # ------------------------------------------------------------------ E-74 / E-75
    async def day(self, d: date) -> DayAnalytics:
        p = await self._period("day", [d])
        return DayAnalytics(date=d, coverage=p.coverage, certainty=p.certainty, by_category=p.by_category, by_tag=p.by_tag, by_task=p.by_task,
                            by_project=p.by_project, work_vs_personal=p.work_vs_personal, sleep=p.sleep, focus=p.focus, ideal=p.ideal,
                            ideal_setup_needed=p.setup_needed)

    async def week(self, start: date) -> WeekAnalytics:
        prefs = await self.prefs()
        if week_start_date(start, prefs.week_start) != start:
            raise ValidationFailed("That date is not the start of a week", path="weekStart", rule="not_week_start")
        p = await self._period("week", date_range(start, start + timedelta(days=6)))
        return WeekAnalytics(from_date=start, to_date=start + timedelta(days=6), coverage=p.coverage, certainty=p.certainty, by_category=p.by_category,
                             by_tag=p.by_tag, by_task=p.by_task, by_project=p.by_project, work_vs_personal=p.work_vs_personal, days=p.days, sleep=p.sleep,
                             focus=p.focus, ideal=p.ideal, ideal_setup_needed=p.setup_needed, prev=p.prev)

    # ------------------------------------------------------------------ E-76 overview
    async def overview(self, scope: str, anchor: date | None) -> OverviewOut:
        prefs = await self.prefs()
        anchor = anchor or self.today
        if scope == "day":
            dates = [anchor]
        else:
            start = week_start_date(anchor, prefs.week_start)
            dates = date_range(start, start + timedelta(days=6))
        p = await self._period(scope, dates)

        banners: list[insights.Banner] = []
        first = await self.q.first_logged_date()
        short_days = [c for c in p.days if c.date < self.today and c.logged > 0 and c.unlogged > prefs.coverage_tolerance_minutes]  # a day with nothing logged is not "short", it is untouched
        if short_days and first is not None and first <= short_days[-1].date:
            c = short_days[-1]
            banners.append(insights.coverage_banner(c.date, c.logged, c.elapsed))
        if p.ideal:
            banners += insights.ideal_banners([r.model_dump() for r in p.ideal.rows if r.root_kind != "sleep"], scope)
        if scope == "week":
            over = [t for t in p.by_tag if t.goal_status == "over" and t.goal_weekly_minutes]
            if over:
                t = max(over, key=lambda x: x.minutes - (x.goal_weekly_minutes or 0))
                banners.append(insights.tag_cap_banner(t.name, str(t.tag_id), t.minutes, t.goal_weekly_minutes or 0))
        if p.sleep.short_nights >= 2:
            banners.append(insights.sleep_banner(p.sleep.short_nights))

        deadlines = []
        for t in await TasksRepository(self.session, self.user.id).open_deadlines(self.today + timedelta(days=7)):
            left = (t.due_date - self.today).days
            deadlines.append(DeadlineOut(task_id=t.id, title=t.title, due_date=t.due_date, days_left=left, overdue=left < 0, priority=t.priority))

        rhythm = None
        if scope == "day":
            lens_filter = ActivityFilters(root_kinds=[k.value for k in self.roots]) if self.roots else None  # the ring and log follow the lens too
            rhythm = (await TimelineService(self.session, self.user).build(anchor, anchor, lens_filter, True)).days[0]

        charts = {
            "actual_vs_ideal": p.ideal.model_dump(mode="json") if p.ideal else None,
            "work_vs_personal": p.work_vs_personal.model_dump(mode="json"),
            "coverage_by_day": [c.model_dump(mode="json") for c in p.days],
            "sleep": p.sleep.model_dump(mode="json"),
            "focus": p.focus.model_dump(mode="json"),
            "categories": [c.model_dump(mode="json") for c in p.by_category],
            "top_tasks": [t.model_dump(mode="json") for t in p.by_task[:5]],
            "tag_goals": [t.model_dump(mode="json") for t in p.by_tag if t.goal_kind != "tracked" and t.goal_weekly_minutes],
            "certainty": p.certainty.model_dump(mode="json"),
        }
        adh = p.ideal.adherence if p.ideal else AdherenceOut(value=None, provisional=scope == "day" and anchor == self.today)
        kpis = Kpis(
            coverage_pct=p.coverage.pct, unlogged_minutes=p.coverage.unlogged, logged_minutes=p.coverage.logged, elapsed_minutes=p.coverage.elapsed, adherence=adh,
            focus={"minutes": p.focus.minutes, "target": p.focus.target}, sleep={"avg_minutes": p.sleep.avg_minutes, "target": p.sleep.target, "drift_minutes": p.sleep.drift_minutes,
                                                                                  "short_nights": p.sleep.short_nights},
            vs_prev={"coverage_pct": pct_change(p.coverage.pct, p.prev.get("coverage_pct")), "focus": (p.focus.minutes - p.prev["focus"]) if p.prev.get("focus") is not None else None,
                     "sleep_avg": (p.sleep.avg_minutes - p.prev["sleep_avg"]) if p.sleep.avg_minutes is not None and p.prev.get("sleep_avg") is not None else None,
                     "adherence": adh.vs_prev},
        )
        return OverviewOut(scope=scope, range={"from": dates[0], "to": dates[-1]}, kpis=kpis,
                           banners=[BannerOut(id=b.id, kind=b.kind, severity=b.severity, text=b.text, action={"label": b.action_label, "route": b.action_route}) for b in insights.pick(banners)],
                           charts=charts, deadlines=deadlines, streaks=await self._streaks(), rhythm=rhythm, ideal_setup_needed=p.setup_needed)

    async def _streaks(self) -> Streaks:
        today = self.today
        dates = await JournalRepository(self.session, self.user.id).confirmed_entry_dates(today - timedelta(days=400))
        cur, journal = (today if today in dates else today - timedelta(days=1)), 0
        while cur in dates:
            journal, cur = journal + 1, cur - timedelta(days=1)
        focus_days = await self.q.focus_by_day(today - timedelta(days=400), today)
        cur, focus = (today if focus_days.get(today, 0) > 0 else today - timedelta(days=1)), 0
        while focus_days.get(cur, 0) > 0:
            focus, cur = focus + 1, cur - timedelta(days=1)
        return Streaks(journal=journal, focus=focus)

    # ------------------------------------------------------------------ E-77 breakdown
    async def breakdown(self, from_date: date, to_date: date, by: str, filters: ActivityFilters | None) -> BreakdownOut:
        if to_date < from_date:
            raise ValidationFailed("'to' must not be before 'from'", path="to", rule="range")
        if (to_date - from_date).days > 366:
            raise AppError("Ranges are limited to 366 days", code="RANGE_TOO_LONG", status=422)
        cats = await self.cats()
        allowed = None
        if filters is not None and any([filters.q, filters.category_ids is not None, filters.tag_ids, filters.task_id, filters.project_id, filters.certainty, filters.needs_review is not None]):
            f = ActivityFilters(**{**filters.__dict__, "from_date": None, "to_date": None})
            allowed = await self.q.filtered_activity_ids(ActivitiesRepository(self.session, self.user.id)._apply(select(Activity.id), f))
        rows = await self.q.slices(from_date, to_date, allowed)
        a = await self._aggregate(rows, await self.q.tags_by_activity(from_date, to_date) if by == "tag" else {})
        waking = sum(m for cid, m in a.by_cat.items() if cid in cats and cats[cid].root_kind != RootKind.sleep)
        total = sum(a.by_cat.values())
        items: list[BreakdownItem] = []
        if by == "category":
            roll: dict[uuid.UUID, int] = defaultdict(int)
            for cid, m in a.by_cat.items():
                for anc in (cats[cid].path_ids if cid in cats else []):
                    roll[anc] += m
            for cid, r in roll.items():
                c = cats.get(cid)
                if c is None:
                    continue
                items.append(BreakdownItem(id=cid, parent_id=c.parent_id, name=c.name, path_names=c.path_names, color=c.color, root_kind=c.root_kind.value, depth=c.depth,
                                           minutes=a.by_cat.get(cid, 0), rollup_minutes=r, share=round(r / waking, 4) if waking and c.root_kind != RootKind.sleep else 0.0))
            items.sort(key=lambda i: (ROOT_ORDER[i.root_kind or "work"], i.path_names or ""))
            kind = "partition"
        else:
            kind = "overlay"
            if by == "tag":
                tags = await self.tags()
                items = [BreakdownItem(id=t, name=tags[t].name, color=tags[t].color, minutes=m, rollup_minutes=m, share=round(m / waking, 4) if waking else 0.0)
                         for t, m in a.by_tag.items() if t in tags]
            elif by == "task":
                tasks = await self.q.tasks(list(a.by_task))
                items = [BreakdownItem(id=t, name=tasks[t].title, color=NEUTRAL, minutes=m, rollup_minutes=m, share=round(m / waking, 4) if waking else 0.0)
                         for t, m in a.by_task.items() if t in tasks]
            elif by == "project":
                projects = await self.q.projects(list(a.by_project))
                items = [BreakdownItem(id=p, name=projects[p].name, color=projects[p].color or NEUTRAL, minutes=m, rollup_minutes=m, share=round(m / waking, 4) if waking else 0.0)
                         for p, m in a.by_project.items() if p in projects]
            else:
                raise ValidationFailed("`by` must be category, tag, task or project", path="by", rule="enum")
            items.sort(key=lambda i: -i.minutes)
        return BreakdownOut(series_kind=kind, by=by, from_date=from_date, to_date=to_date, items=items, total_minutes=total, waking_minutes=waking)

    # ------------------------------------------------------------------ E-78 trends
    async def trends(self, metric: str, granularity: str, periods: int) -> TrendsOut:
        if metric not in ("adherence", "coverage", "sleep", "focus"):
            raise ValidationFailed("Unknown metric", path="metric", rule="enum")
        if granularity not in ("day", "week"):
            raise ValidationFailed("Unknown granularity", path="granularity", rule="enum")
        if not 1 <= periods <= MAX_TREND_PERIODS[granularity]:
            raise ValidationFailed(f"periods must be 1 to {MAX_TREND_PERIODS[granularity]} for {granularity} granularity", path="periods", rule="range")
        prefs, cats = await self.prefs(), await self.cats()
        if granularity == "week":
            last = week_start_date(self.today, prefs.week_start)
            starts = [last - timedelta(days=7 * i) for i in reversed(range(periods))]
            spans = [date_range(s, s + timedelta(days=6)) for s in starts]
        else:
            starts = [self.today - timedelta(days=i) for i in reversed(range(periods))]
            spans = [[s] for s in starts]
        lo, hi = spans[0][0], spans[-1][-1]
        rows = await self.q.slices(lo, hi)
        a = await self._aggregate(rows, {})
        kind = IdealKind.day if granularity == "day" else IdealKind.week
        versions = await self._templates(kind)
        day_versions = versions if kind == IdealKind.day else await self._templates(IdealKind.day)
        nights = sleep.attribute(await self.q.sleep_activities(lo, hi, self.tz), self.tz) if metric == "sleep" and self.sleep_in_lens else {}

        def focus_target(v) -> float | None:
            return sum(al.minutes for al in v[1] if al.category_id in cats and cats[al.category_id].counts_as_focus and self.in_lens(cats[al.category_id])) if v else None

        points: list[TrendPoint] = []
        for dates in spans:
            start = dates[0]
            if dates[0] > self.today:
                points.append(TrendPoint(period_start=start, value=None))
                continue
            value: float | None
            target: float | None = None
            if metric == "coverage":
                el = sum(self.elapsed(d) for d in dates)
                logged = sum(a.placed.get(d, 0) + a.unplaced.get(d, 0) for d in dates)
                value = coverage_of(logged, el) if el else None
            elif metric == "focus":
                value = float(sum(a.focus.get(d, 0) for d in dates))
                target = focus_target(self._in_force(versions, start)) or None
            elif metric == "sleep":
                got = [nights[d].minutes for d in dates if d in nights]
                value = round(sum(got) / len(got)) if got else None
                dv = self._in_force(day_versions, start)
                target = float(sum(al.minutes for al in dv[1] if cats[al.category_id].root_kind == RootKind.sleep)) if dv and self.sleep_in_lens else None
            else:
                cmp = await self._compare(kind, dates, a.by_day_cat, self._in_force(versions, start))
                value = cmp.adherence.value if cmp else None
            points.append(TrendPoint(period_start=start, value=value, target=target))
        return TrendsOut(metric=metric, granularity=granularity, points=points)


__all__ = ["AnalyticsService"]
