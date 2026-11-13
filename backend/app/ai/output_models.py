"""Pydantic models equal to extraction schema v1 (PRD 6.5). Parsing is lenient on extras and strict on shape."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TimeOfDay(_Loose):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    meridiem: Literal["am", "pm"] | None = None

    @field_validator("meridiem", mode="before")
    @classmethod
    def _norm(cls, v):
        return v.lower() if isinstance(v, str) and v.lower() in ("am", "pm") else (None if v in ("", "null", None) else v)


class WindowRef(_Loose):
    label: Literal["morning", "afternoon", "evening", "night"] | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None


class TimeRef(_Loose):
    kind: Literal["range", "duration", "point", "vague", "none"] = "none"
    start: TimeOfDay | None = None
    end: TimeOfDay | None = None
    start_anchor: Literal["previous_end"] | None = None
    end_anchor: Literal["next_start"] | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    approximate: bool = False
    window: WindowRef | None = None
    day_offset: int = Field(default=0, ge=-7, le=7)
    quote: str | None = None


class TagProposal(_Loose):
    tag_id: str | None = None
    name: str = ""
    new: bool = False
    reason: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class TaskProposal(_Loose):
    task_id: str | None = None
    new_task_title: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class Confidences(_Loose):
    overall: float = Field(default=0.8, ge=0, le=1)
    time: float = Field(default=0.8, ge=0, le=1)
    category: float = Field(default=0.8, ge=0, le=1)


class ExtractedActivity(_Loose):
    temp_id: str
    order: int = 0
    title: str = Field(min_length=1, max_length=400)
    description: str | None = None
    source_quote: str = ""
    category_id: str = ""
    time_ref: TimeRef = Field(default_factory=TimeRef)
    tags: list[TagProposal] = Field(default_factory=list)
    task: TaskProposal | None = None
    location_type: Literal["office", "home", "remote", "travel", "other"] | None = None
    confidence: Confidences = Field(default_factory=Confidences)
    flags: list[str] = Field(default_factory=list)

    @field_validator("location_type", mode="before")
    @classmethod
    def _loc(cls, v):
        return v if v in ("office", "home", "remote", "travel", "other") else None


class ExtractionOutput(_Loose):
    schema_version: str = "1"
    entry_summary: str = ""
    activities: list[ExtractedActivity] = Field(default_factory=list, max_length=60)
    clarifications: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
