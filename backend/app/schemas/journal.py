import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import EntryStatus, InputMethod
from app.schemas.activity import ActivityOut
from app.schemas.common import ORM, Str


class EntryCreate(BaseModel):
    raw_text: str = Field(min_length=1, max_length=10_000)
    covers_start_at: datetime
    covers_end_at: datetime
    timezone: str | None = None
    input_method: InputMethod = InputMethod.typed
    dictation_seconds: int | None = Field(default=None, ge=0, le=36_000)


class EntryPatch(BaseModel):
    version: int
    raw_text: str | None = Field(default=None, min_length=1, max_length=10_000)
    covers_start_at: datetime | None = None
    covers_end_at: datetime | None = None
    title: Str | None = Field(default=None, max_length=120)


class EntryOut(ORM):
    id: uuid.UUID
    entry_date: date
    title: str | None
    raw_text: str
    covers_start_at: datetime
    covers_end_at: datetime
    timezone: str
    input_method: InputMethod
    dictation_seconds: int | None
    status: EntryStatus
    latest_job_id: uuid.UUID | None
    revision: int
    version: int
    created_at: datetime
    updated_at: datetime


class TagDot(BaseModel):
    name: str
    color: str


class EntrySummary(BaseModel):
    id: uuid.UUID
    entry_date: date
    title: str
    status: EntryStatus
    covers_start_at: datetime
    covers_end_at: datetime
    timezone: str
    input_method: InputMethod
    word_count: int
    activity_count: int
    covered_minutes: int
    window_minutes: int
    tags: list[TagDot]


class JobBrief(BaseModel):
    id: uuid.UUID
    status: str
    error_code: str | None
    is_stale: bool
    provider: str
    model: str


class EntryDetail(EntryOut):
    activities: list[ActivityOut]
    latest_job: JobBrief | None


class RevisionOut(ORM):
    revision: int
    raw_text: str
    covers_start_at: datetime
    covers_end_at: datetime
    created_at: datetime


class YesterdayGap(BaseModel):
    date: date
    minutes: int
    start_at: datetime
    end_at: datetime


class StatsOut(BaseModel):
    streak_days: int
    entries_per_day_30d: float
    full_days_pct_30d: float | None
    yesterday_gap: YesterdayGap | None


class ProcessIn(BaseModel):
    regenerate: bool = False
    user_hint: Str | None = Field(default=None, max_length=500)


class ProcessOut(BaseModel):
    job_id: uuid.UUID
    status: str


class JobOut(BaseModel):
    id: uuid.UUID
    status: str
    attempts: int
    error_code: str | None
    entry_id: uuid.UUID
    is_stale: bool


class AiStatusOut(BaseModel):
    provider: str
    model: str
    demo: bool
    enabled: bool
    daily_limit: int
    used_today: int
