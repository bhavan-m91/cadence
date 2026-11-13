"""Python enums mirroring the PostgreSQL enum types created in migration 0001."""

import enum

from sqlalchemy.dialects.postgresql import ENUM as PGEnum


class S(enum.StrEnum):
    pass


class Theme(S):
    system = "system"
    light = "light"
    dark = "dark"


class TimeFormat(S):
    h12 = "12h"
    h24 = "24h"


class CoveragePreset(S):
    whole_day = "whole_day"
    last_hours = "last_hours"
    since_last = "since_last"
    custom = "custom"


class TranscriptionMode(S):
    auto = "auto"
    server_only = "server_only"
    browser_only = "browser_only"


class EmailTokenPurpose(S):
    verify_email = "verify_email"
    reset_password = "reset_password"


class AuthEventType(S):
    login_ok = "login_ok"
    login_fail = "login_fail"
    logout = "logout"
    password_changed = "password_changed"
    reset_requested = "reset_requested"
    reset_done = "reset_done"
    google_linked = "google_linked"


class InputMethod(S):
    typed = "typed"
    dictated = "dictated"


class EntryStatus(S):
    draft = "draft"
    processing = "processing"
    review = "review"
    confirmed = "confirmed"
    failed = "failed"
    manual = "manual"


class AiJobType(S):
    extract_activities = "extract_activities"


class AiJobStatus(S):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class TaskStatus(S):
    open = "open"
    done = "done"
    dropped = "dropped"


class RootKind(S):
    work = "work"
    personal = "personal"
    sleep = "sleep"


class GoalKind(S):
    tracked = "tracked"
    min = "min"
    max = "max"


class ActivityStatus(S):
    draft = "draft"
    confirmed = "confirmed"


class ActivityKind(S):
    actual = "actual"
    planned = "planned"


class LocationType(S):
    office = "office"
    home = "home"
    remote = "remote"
    travel = "travel"
    other = "other"


class Placement(S):
    placed = "placed"
    unplaced = "unplaced"


class TimeCertainty(S):
    stated = "stated"
    inferred = "inferred"
    estimated = "estimated"


class ActivityOrigin(S):
    ai = "ai"
    manual = "manual"
    split = "split"
    merge = "merge"
    duplicate = "duplicate"


class TagSource(S):
    ai = "ai"
    rule = "rule"
    alias = "alias"
    user = "user"


class ActivityEventType(S):
    created = "created"
    edited = "edited"
    tagged = "tagged"
    untagged = "untagged"
    task_linked = "task_linked"
    split = "split"
    merged = "merged"
    duplicated = "duplicated"
    approved = "approved"
    deleted = "deleted"
    restored = "restored"


class EventActor(S):
    user = "user"
    ai = "ai"
    system = "system"


class IdealKind(S):
    day = "day"
    week = "week"


class IdealDistribution(S):
    all_days = "all_days"
    weekdays = "weekdays"
    weekend = "weekend"


class ExportStatus(S):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    expired = "expired"


class KeywordTarget(S):
    tag = "tag"
    category = "category"


def pg_enum(cls: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(cls, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])
