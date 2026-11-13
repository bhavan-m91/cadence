import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import ActivityKind, LocationType, TimeCertainty
from app.schemas.activity import ActivityTagOut
from app.schemas.taxonomy import CategoryChip


class Block(BaseModel):
    id: uuid.UUID
    version: int
    title: str
    kind: ActivityKind
    start_at: datetime
    end_at: datetime
    minutes: int
    category: CategoryChip
    tags: list[ActivityTagOut]
    time_certainty: TimeCertainty
    needs_review: bool
    flags: list[str]
    continues_from_previous_day: bool
    continues_to_next_day: bool
    location_type: LocationType | None


class UnplacedItem(BaseModel):
    id: uuid.UUID
    title: str
    minutes: int
    category: CategoryChip
    window_start_at: datetime | None
    window_end_at: datetime | None


class Gap(BaseModel):
    start_at: datetime
    end_at: datetime
    minutes: int


class Coverage(BaseModel):
    placed: int
    logged: int
    elapsed: int
    unlogged: int
    pct: float
    complete: bool


class IdealRow(BaseModel):
    category_id: uuid.UUID
    name: str
    color: str
    minutes: int


class DayTimeline(BaseModel):
    date: date
    day_start_at: datetime
    day_end_at: datetime
    blocks: list[Block]
    planned: list[Block]
    unplaced: list[UnplacedItem]
    gaps: list[Gap]
    coverage: Coverage
    ideal: list[IdealRow] | None = None


class TimelineOut(BaseModel):
    days: list[DayTimeline]
    timezone: str
