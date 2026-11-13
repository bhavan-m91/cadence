"""One implementation of the time rules (PRD 5.3): UTC instants, IANA zones, local days, day slices.

Day = local midnight to next local midnight; on DST days a day is 23 or 25 hours long. Elapsed instants make
slicing DST-correct without special cases.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import AppError, ValidationFailed


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise ValidationFailed(f"Unknown timezone '{name}'", path="timezone", rule="invalid_timezone") from e


def ensure_utc(dt: datetime, tz: ZoneInfo | None = None) -> datetime:
    """Normalise a datetime to UTC. Naive values are interpreted in `tz` (or rejected when none is given)."""
    if dt.tzinfo is None:
        if tz is None:
            raise ValidationFailed("Datetime needs an offset", rule="offset_required")
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def local_date_of(instant: datetime, tz: ZoneInfo) -> date:
    return instant.astimezone(tz).date()


def day_start(d: date, tz: ZoneInfo) -> datetime:
    """UTC instant of local midnight at the start of `d`."""
    return datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC)


def day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return day_start(d, tz), day_start(d + timedelta(days=1), tz)


def elapsed_minutes(d: date, tz: ZoneInfo) -> int:
    s, e = day_bounds(d, tz)
    return int((e - s).total_seconds() // 60)


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def parse_local(d: date, t: time, tz: ZoneInfo) -> datetime:
    """Local intent -> UTC. Refuses nonexistent local times (spring-forward gap) with INVALID_LOCAL_TIME."""
    naive = datetime.combine(d, t)
    aware = naive.replace(tzinfo=tz)
    if aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
        raise AppError("That local time does not exist (clock change)", code="INVALID_LOCAL_TIME", status=422)
    return aware.astimezone(UTC)


def week_start_date(d: date, week_start: int) -> date:
    """`week_start`: 1 = Monday ... 7 = Sunday."""
    return d - timedelta(days=(d.isoweekday() - week_start) % 7)


@dataclass(frozen=True)
class DaySlice:
    local_date: date
    minutes: int
    start: datetime
    end: datetime


def compute_slices(start: datetime, end: datetime, tz: ZoneInfo) -> list[DaySlice]:
    """Clip the placed interval [start, end) to local days (PRD 5.3 slice algorithm)."""
    if end <= start:
        raise ValueError("end must be after start")
    out: list[DaySlice] = []
    d = local_date_of(start, tz)
    last = local_date_of(end - timedelta(microseconds=1), tz)
    while d <= last:
        d_start, d_end = day_bounds(d, tz)
        s, e = max(start, d_start), min(end, d_end)
        minutes = int((e - s).total_seconds() // 60)
        if minutes > 0:
            out.append(DaySlice(d, minutes, s, e))
        d += timedelta(days=1)
    return out


def ymd_label(d: date) -> str:
    """'Wed 11 Nov' for banner text (no leading zero, locale independent)."""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"
