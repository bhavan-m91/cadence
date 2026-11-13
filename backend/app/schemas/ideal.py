import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import IdealDistribution, RootKind


class AllocationIn(BaseModel):
    category_id: uuid.UUID
    minutes: int
    distribution: IdealDistribution = IdealDistribution.all_days


class IdealSaveIn(BaseModel):
    effective_from: date
    allocations: list[AllocationIn] = Field(max_length=200)


class AllocationOut(BaseModel):
    category_id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: RootKind
    minutes: int
    distribution: IdealDistribution
    per_day_minutes: int | None = None


class IdealTemplateOut(BaseModel):
    kind: Literal["day", "week"]
    effective_from: date | None
    allocations: list[AllocationOut]
    total_minutes: int
    expected_minutes: int
    unallocated_minutes: int


class IdealVersion(BaseModel):
    effective_from: date
    created_at: datetime
    total_minutes: int


class IdealOverviewOut(BaseModel):
    current: IdealTemplateOut | None
    versions: list[IdealVersion]


class ProgressRow(BaseModel):
    category_id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: RootKind
    distribution: IdealDistribution
    target: int
    expected_to_date: int
    actual: int
    delta: int
    status: Literal["on_target", "under", "over"]


class ProgressOut(BaseModel):
    scope: Literal["day", "week"]
    from_date: date
    to_date: date
    as_of: date
    template_effective_from: date | None
    provisional: bool
    rows: list[ProgressRow]
    other_actual: int
    total_target: int
    total_actual: int
