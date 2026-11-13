import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CoveragePreset, ExportStatus, Theme, TimeFormat, TranscriptionMode
from app.schemas.common import ORM, Str


class ProfilePatch(BaseModel):
    display_name: Str | None = Field(default=None, min_length=1, max_length=80)
    role_title: Str | None = Field(default=None, max_length=80)
    timezone: str | None = None
    theme: Theme | None = None


class PreferencesOut(ORM):
    week_start: int
    time_format: TimeFormat
    coverage_tolerance_minutes: int
    gap_min_minutes: int
    short_night_minutes: int
    office_start_minute: int
    office_end_minute: int
    ai_enabled: bool
    default_coverage_preset: CoveragePreset
    transcription_mode: TranscriptionMode


class PreferencesPatch(BaseModel):
    week_start: int | None = Field(default=None, ge=1, le=7)
    time_format: TimeFormat | None = None
    coverage_tolerance_minutes: int | None = Field(default=None, ge=0, le=60)
    gap_min_minutes: int | None = Field(default=None, ge=1, le=60)
    short_night_minutes: int | None = Field(default=None, ge=240, le=600)
    office_start_minute: int | None = Field(default=None, ge=0, le=1440)
    office_end_minute: int | None = Field(default=None, ge=0, le=1440)
    ai_enabled: bool | None = None
    default_coverage_preset: CoveragePreset | None = None
    transcription_mode: TranscriptionMode | None = None

    @model_validator(mode="after")
    def _office(self) -> "PreferencesPatch":
        s, e = self.office_start_minute, self.office_end_minute
        if s is not None and e is not None and s >= e:
            raise ValueError("office_start_minute must be before office_end_minute")
        return self


class OnboardingIn(BaseModel):
    timezone: str
    seed: Literal["default", "empty"] = "default"
    ideal_day_preset: Literal["balanced", "none"] = "balanced"


class OnboardingOut(BaseModel):
    categories_created: int
    tags_created: int


class ExportOut(ORM):
    id: uuid.UUID
    status: ExportStatus
    download_url: str | None = None
    expires_at: datetime | None = None
