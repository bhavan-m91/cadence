"""Sleep by wake date (FR-129, AC-063): a night counts fully on the local date its sleep ENDS."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.analytics.metrics import bedtime_drift, bedtime_minutes_after_18


@dataclass
class SleepActivity:
    minutes: int
    placed: bool
    start_at: datetime | None
    end_at: datetime | None
    local_date: date  # the activity's own start date; used when there is no end instant


@dataclass
class Night:
    date: date
    minutes: int
    bed_at: datetime | None
    wake_at: datetime | None


def attribute(acts: list[SleepActivity], tz: ZoneInfo) -> dict[date, Night]:
    """Sum sleep per wake date. Duration-only sleep counts toward the total but has no bed or wake time."""
    out: dict[date, Night] = {}
    for a in acts:
        wake = a.end_at.astimezone(tz).date() if a.placed and a.end_at else a.local_date
        n = out.setdefault(wake, Night(wake, 0, None, None))
        n.minutes += a.minutes
        if a.placed and a.start_at and a.end_at:
            n.bed_at = a.start_at if n.bed_at is None or a.start_at < n.bed_at else n.bed_at
            n.wake_at = a.end_at if n.wake_at is None or a.end_at > n.wake_at else n.wake_at
    return out


def summarize(nights: dict[date, Night], dates: list[date], tz: ZoneInfo, short_night_minutes: int) -> dict:
    """Per-night rows for `dates` plus average, shortest, longest, short-night count and bedtime drift."""
    rows = [nights[d] for d in dates if d in nights]
    mins = [n.minutes for n in rows]
    beds = []
    for n in rows:
        if n.bed_at:
            local = n.bed_at.astimezone(tz)
            beds.append(bedtime_minutes_after_18(local.hour, local.minute))
    return {
        "avg_minutes": round(sum(mins) / len(mins)) if mins else None,
        "shortest": min(mins) if mins else None,
        "longest": max(mins) if mins else None,
        "short_nights": sum(1 for m in mins if m < short_night_minutes),
        "drift_minutes": bedtime_drift(beds),
    }
