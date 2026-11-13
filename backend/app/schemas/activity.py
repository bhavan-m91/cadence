import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    ActivityEventType,
    ActivityKind,
    ActivityOrigin,
    ActivityStatus,
    EventActor,
    LocationType,
    Placement,
    TimeCertainty,
)
from app.schemas.common import ORM, Str
from app.schemas.task import TaskOut
from app.schemas.taxonomy import CategoryChip, TagChip


class ActivityTagOut(BaseModel):
    tag_id: uuid.UUID
    name: str
    color: str
    source: str
    confidence: Decimal | None = None
    reason: str | None = None


class ActivityOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: ActivityStatus
    kind: ActivityKind
    placement: Placement
    start_at: datetime | None
    end_at: datetime | None
    window_start_at: datetime | None
    window_end_at: datetime | None
    duration_minutes: int | None
    time_certainty: TimeCertainty
    timezone: str
    local_date: date
    category: CategoryChip
    tags: list[ActivityTagOut]
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    location_type: LocationType | None
    origin: ActivityOrigin
    confidence: Decimal | None
    needs_review: bool
    flags: list[str]
    user_edited: bool
    journal_entry_id: uuid.UUID | None
    derived_from_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class SourceContext(BaseModel):
    quote: str | None
    context_before: str | None = None
    context_after: str | None = None
    entry_id: uuid.UUID | None = None


class AlsoTagged(BaseModel):
    id: uuid.UUID
    title: str
    start_at: datetime | None
    duration_minutes: int | None


class ActivityDetail(ActivityOut):
    task: TaskOut | None = None
    source: SourceContext
    also_tagged: list[AlsoTagged]


class _TimeFields(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None


class ActivityCreate(_TimeFields):
    title: Str = Field(min_length=1, max_length=120)
    description: Str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    location_type: LocationType | None = None
    kind: ActivityKind = ActivityKind.actual
    time_certainty: TimeCertainty = TimeCertainty.stated
    timezone: str | None = None

    @model_validator(mode="after")
    def _times(self) -> "ActivityCreate":
        placed = self.start_at is not None or self.end_at is not None
        if placed and (self.start_at is None or self.end_at is None):
            raise ValueError("start_at and end_at must be sent together")
        if not placed and not (self.duration_minutes and self.window_start_at and self.window_end_at):
            raise ValueError("Send start_at + end_at, or duration_minutes + window_start_at + window_end_at")
        return self


class ActivityPatch(_TimeFields):
    version: int
    title: Str | None = Field(default=None, min_length=1, max_length=120)
    description: Str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    location_type: LocationType | None = None
    time_certainty: TimeCertainty | None = None
    clear: list[Literal["task_id", "project_id", "location_type", "description"]] = Field(default_factory=list)


class SplitIn(BaseModel):
    at: datetime


class SplitOut(BaseModel):
    original: ActivityOut
    created: ActivityOut


class MergeIn(BaseModel):
    activity_ids: list[uuid.UUID] = Field(min_length=2, max_length=20)
    category_id: uuid.UUID | None = None
    title: Str | None = Field(default=None, min_length=1, max_length=120)


class DuplicateIn(BaseModel):
    start_at: datetime | None = None


class TagsPut(BaseModel):
    tag_ids: list[uuid.UUID] = Field(max_length=30)


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    op: Literal["add_tags", "remove_tags", "set_category", "set_task", "set_project", "delete"]
    value: list[uuid.UUID] | uuid.UUID | None = None


class BulkOut(BaseModel):
    updated: int


class MarkDoneIn(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None


class EventOut(ORM):
    id: uuid.UUID
    event_type: ActivityEventType
    actor: EventActor
    payload: dict | None
    created_at: datetime


__all__ = ["TagChip"]
