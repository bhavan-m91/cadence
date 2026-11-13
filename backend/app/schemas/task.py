import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import TaskStatus
from app.schemas.common import ORM, Color, Str


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    color: str | None
    archived: bool = False
    task_count: int = 0
    logged_minutes: int = 0


class ProjectCreate(BaseModel):
    name: Str = Field(min_length=1, max_length=80)
    color: Color | None = None


class ProjectPatch(BaseModel):
    name: Str | None = Field(default=None, min_length=1, max_length=80)
    color: Color | None = None
    archived: bool | None = None


class TaskOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    project_id: uuid.UUID | None
    priority: int | None
    due_date: date | None
    status: TaskStatus
    estimate_minutes: int | None
    completed_at: datetime | None
    version: int
    logged_minutes: int = 0
    days_left: int | None = None
    overdue: bool = False


class TaskCreate(BaseModel):
    title: Str = Field(min_length=1, max_length=160)
    description: Str | None = Field(default=None, max_length=4000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    due_date: date | None = None
    estimate_minutes: int | None = Field(default=None, gt=0)


class TaskPatch(BaseModel):
    version: int | None = None
    title: Str | None = Field(default=None, min_length=1, max_length=160)
    description: Str | None = Field(default=None, max_length=4000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    due_date: date | None = None
    status: TaskStatus | None = None
    estimate_minutes: int | None = Field(default=None, gt=0)
    clear: list[str] = Field(default_factory=list, description="Fields to set to null: project_id, priority, due_date, estimate_minutes, description")


class RollupPoint(BaseModel):
    key: str
    minutes: int


class TaskRollup(BaseModel):
    total_minutes: int
    by_week: list[RollupPoint]
    by_day: list[RollupPoint]
    first_logged: date | None
    last_logged: date | None
