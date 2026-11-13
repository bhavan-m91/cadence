import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import IdealDistribution
from app.schemas.timeline import DayTimeline

RowStatus = Literal["on_target", "under", "over"]


class CategoryTotal(BaseModel):
    category_id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: str
    minutes: int
    share: float  # of waking time (Sleep excluded), 0 for Sleep itself


class TagTotal(BaseModel):
    tag_id: uuid.UUID
    name: str
    color: str
    minutes: int
    share: float
    goal_kind: str
    goal_weekly_minutes: int | None
    goal_status: str


class TaskTotal(BaseModel):
    task_id: uuid.UUID
    title: str
    project_id: uuid.UUID | None
    minutes: int


class ProjectTotal(BaseModel):
    project_id: uuid.UUID
    name: str
    minutes: int


class CoverageOut(BaseModel):
    placed: int
    unplaced: int
    logged: int
    elapsed: int
    unlogged: int
    pct: float
    complete: bool


class CertaintyOut(BaseModel):
    recorded: int
    estimated: int


class WorkPersonal(BaseModel):
    work: int
    personal: int
    work_outside_office: int
    personal_in_office_hours: int


class AdherenceOut(BaseModel):
    value: float | None
    provisional: bool
    vs_prev: float | None = None


class IdealCompareRow(BaseModel):
    category_id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: str
    distribution: IdealDistribution | None
    target: int
    expected: int
    actual: int
    delta: int
    status: RowStatus


class IdealCompare(BaseModel):
    kind: Literal["day", "week"]
    effective_from: date | None
    rows: list[IdealCompareRow]
    unallocated_actual: int  # tracked time outside every allocation (FR-127)
    adherence: AdherenceOut


class SleepNight(BaseModel):
    date: date
    minutes: int
    bed_at: datetime | None
    wake_at: datetime | None
    short: bool


class SleepBlock(BaseModel):
    nights: list[SleepNight]
    avg_minutes: int | None
    target: int | None
    drift_minutes: int | None
    shortest: int | None
    longest: int | None
    short_nights: int


class FocusDay(BaseModel):
    date: date
    minutes: int


class FocusBlock(BaseModel):
    days: list[FocusDay]
    minutes: int
    target: int | None


class DayColumn(BaseModel):
    date: date
    placed: int
    unplaced: int
    logged: int
    elapsed: int
    unlogged: int
    complete: bool
    focus: int
    sleep: int


class DayAnalytics(BaseModel):
    date: date
    coverage: CoverageOut
    certainty: CertaintyOut
    by_category: list[CategoryTotal]
    by_tag: list[TagTotal]
    by_task: list[TaskTotal]
    by_project: list[ProjectTotal]
    work_vs_personal: WorkPersonal
    sleep: SleepBlock
    focus: FocusBlock
    ideal: IdealCompare | None
    ideal_setup_needed: bool


class WeekAnalytics(BaseModel):
    from_date: date
    to_date: date
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
    ideal_setup_needed: bool
    prev: dict[str, float | int | None]


class BannerOut(BaseModel):
    id: str
    kind: str
    severity: str
    text: str
    action: dict[str, str]


class DeadlineOut(BaseModel):
    task_id: uuid.UUID
    title: str
    due_date: date
    days_left: int
    overdue: bool
    priority: int | None


class Kpis(BaseModel):
    coverage_pct: float
    unlogged_minutes: int
    logged_minutes: int
    elapsed_minutes: int
    adherence: AdherenceOut
    focus: dict[str, int | None]
    sleep: dict[str, int | None]
    vs_prev: dict[str, float | int | None]


class Streaks(BaseModel):
    journal: int
    focus: int


class OverviewOut(BaseModel):
    scope: Literal["day", "week"]
    range: dict[str, date]
    kpis: Kpis
    banners: list[BannerOut]
    charts: dict
    deadlines: list[DeadlineOut]
    streaks: Streaks
    rhythm: DayTimeline | None
    ideal_setup_needed: bool


class BreakdownItem(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    name: str
    path_names: str | None = None
    color: str
    root_kind: str | None = None
    depth: int | None = None
    minutes: int  # own time for a category, total for an overlay
    rollup_minutes: int  # own time plus every descendant (equal to `minutes` for overlays)
    share: float


class BreakdownOut(BaseModel):
    series_kind: Literal["partition", "overlay"]
    by: str
    from_date: date
    to_date: date
    items: list[BreakdownItem]
    total_minutes: int
    waking_minutes: int


class TrendPoint(BaseModel):
    period_start: date
    value: float | None
    target: float | None = None


class TrendsOut(BaseModel):
    metric: str
    granularity: str
    points: list[TrendPoint]
