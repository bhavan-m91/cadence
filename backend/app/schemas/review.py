import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import LocationType
from app.schemas.activity import ActivityOut
from app.schemas.common import Str
from app.schemas.journal import JobBrief


class ReviewTag(BaseModel):
    tag_id: uuid.UUID | None
    name: str
    color: str
    source: str
    confidence: float
    reason: str | None
    applied: bool
    new: bool


class ReviewCategory(BaseModel):
    id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: str


class ReviewTask(BaseModel):
    task_id: uuid.UUID | None
    task_title: str | None
    new_task_title: str | None
    confidence: float


class ReviewSource(BaseModel):
    quote: str | None
    start: int | None
    end: int | None


class DuplicateRef(BaseModel):
    id: uuid.UUID
    title: str
    start_at: datetime | None


class ReviewDraft(BaseModel):
    id: uuid.UUID
    temp_id: str
    order: int
    title: str
    description: str | None
    placement: Literal["placed", "unplaced"]
    start_at: datetime | None
    end_at: datetime | None
    window_start_at: datetime | None
    window_end_at: datetime | None
    duration_minutes: int | None
    time_certainty: str
    category: ReviewCategory
    tags: list[ReviewTag]
    task: ReviewTask
    location_type: LocationType | None
    confidence: float
    band: Literal["high", "medium", "low"]
    flags: list[str]
    source: ReviewSource
    include: bool
    duplicate_of: DuplicateRef | None
    ideal_row_id: uuid.UUID | None


class ReviewGap(BaseModel):
    start_at: datetime
    end_at: datetime
    minutes: int


class ReviewConflict(BaseModel):
    draft_id: uuid.UUID
    other_id: uuid.UUID
    other_title: str
    other_is_draft: bool
    start_at: datetime
    end_at: datetime
    overlap_minutes: int


class Question(BaseModel):
    id: str
    type: str
    activity_temp_id: str
    prompt: str
    options: list[dict[str, str]]


class Blocker(BaseModel):
    draft_id: uuid.UUID
    reason: Literal["UNANSWERED_QUESTION", "MISSING_DURATION", "OVERLAP"]


class ReviewSummary(BaseModel):
    activity_count: int
    covered_minutes: int
    not_mentioned_minutes: int
    gap_count: int
    to_double_check: int
    tags_applied: int


class IdealRowOut(BaseModel):
    category_id: uuid.UUID
    name: str
    color: str
    target: int
    actual: int


class IdealPreview(BaseModel):
    date: date
    rows: list[IdealRowOut]
    other_actual: int


class ReplaceCandidate(BaseModel):
    id: uuid.UUID
    title: str
    user_edited: bool


class ReviewEntry(BaseModel):
    id: uuid.UUID
    status: str
    title: str | None
    raw_text: str
    covers_start_at: datetime
    covers_end_at: datetime
    timezone: str
    revision: int
    input_method: str
    dictation_seconds: int | None


class ReviewOut(BaseModel):
    entry: ReviewEntry
    job: JobBrief
    summary: ReviewSummary
    drafts: list[ReviewDraft]
    gaps: list[ReviewGap]
    conflicts: list[ReviewConflict]
    questions: list[Question]
    blocking: list[Blocker]
    warnings: list[str]
    ideal: IdealPreview | None
    replace_candidates: list[ReplaceCandidate]


class AnswerIn(BaseModel):
    job_id: uuid.UUID
    question_id: str
    value: str = Field(max_length=64)


class CommitEdit(BaseModel):
    title: Str | None = Field(default=None, min_length=1, max_length=120)
    description: Str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=30)
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    task_id: uuid.UUID | None = None
    new_task_title: Str | None = Field(default=None, min_length=1, max_length=160)
    clear_task: bool = False
    location_type: LocationType | None = None


class CommitActivity(BaseModel):
    draft_id: uuid.UUID
    include: bool = True
    edits: CommitEdit | None = None


class NewTagChoice(BaseModel):
    draft_id: uuid.UUID
    name: Str = Field(min_length=1, max_length=48)
    keep: bool = True


class Transition(BaseModel):
    start_at: datetime
    end_at: datetime


class ConflictResolution(BaseModel):
    draft_id: uuid.UUID
    action: Literal["trim_new", "trim_existing", "replace_existing", "keep_unplaced"]
    existing_id: uuid.UUID | None = None


class CommitIn(BaseModel):
    job_id: uuid.UUID
    replace_previous: bool = False
    activities: list[CommitActivity] = Field(default_factory=list, max_length=60)
    new_tags: list[NewTagChoice] = Field(default_factory=list, max_length=60)
    transitions: list[Transition] = Field(default_factory=list, max_length=30)
    conflict_resolutions: list[ConflictResolution] = Field(default_factory=list, max_length=60)


class CommitOut(BaseModel):
    activities: list[ActivityOut]
    created_tags: list[str]
    created_tasks: list[str]
    replaced: list[uuid.UUID]
    kept_edited: list[uuid.UUID]


__all__ = ["Any"]
