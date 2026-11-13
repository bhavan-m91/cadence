"""Pure metric formulas (PRD 9.3). No I/O here: callers pass numbers in and get numbers or labels out."""

from datetime import date, timedelta

from app.models.enums import IdealDistribution

STATUS_FLOOR_MINUTES = 15
STATUS_PCT = 0.10


def row_status(delta: int, target: int) -> str:
    """FR-119: `on_target` when |delta| <= max(15 min, 10% of target); otherwise `under` or `over`."""
    if abs(delta) <= max(STATUS_FLOOR_MINUTES, round(target * STATUS_PCT)):
        return "on_target"
    return "under" if delta < 0 else "over"


def distribution_days(distribution: IdealDistribution, week_dates: list[date]) -> list[date]:
    """Days of the week a weekly allocation is spread over. Weekdays are Monday to Friday, weekend Saturday and Sunday."""
    if distribution == IdealDistribution.weekdays:
        return [d for d in week_dates if d.isoweekday() <= 5]
    if distribution == IdealDistribution.weekend:
        return [d for d in week_dates if d.isoweekday() >= 6]
    return list(week_dates)


def per_day_minutes(weekly_minutes: int, distribution: IdealDistribution) -> int:
    n = {IdealDistribution.all_days: 7, IdealDistribution.weekdays: 5, IdealDistribution.weekend: 2}[distribution]
    return round(weekly_minutes / n)


def pace_expected(weekly_minutes: int, distribution: IdealDistribution, week_dates: list[date], through: date) -> int:
    """Where you should be at the end of `through` (AC-052: 1,200 min on weekdays is 720 by Wednesday's end)."""
    days = distribution_days(distribution, week_dates)
    if not days:
        return 0
    elapsed = sum(1 for d in days if d <= through)
    return round(weekly_minutes * elapsed / len(days))


def prorate(target: int, elapsed_minutes: int, day_minutes: int) -> int:
    """Today's target scaled by how much of the day has passed (D-07: today is provisional)."""
    if day_minutes <= 0:
        return target
    return round(target * min(1.0, max(0.0, elapsed_minutes / day_minutes)))


def coverage(logged: int, elapsed: int) -> float:
    """Share of the elapsed time that is accounted for (a day that has not started is 100%, nothing is missing yet)."""
    return round(min(1.0, logged / elapsed), 4) if elapsed > 0 else 1.0


def adherence(pairs: list[tuple[int, int]]) -> float | None:
    """FR-126 / AC-061: sum of min(actual, target) over the sum of targets. `None` when there is nothing to hold you to."""
    total = sum(t for _, t in pairs)
    if total <= 0:
        return None
    return round(sum(min(a, t) for a, t in pairs) / total, 4)


def bedtime_minutes_after_18(hour: int, minute: int) -> int:
    """Bedtime as minutes after 18:00 local, so 23:30 is 330 and 01:00 is 420 (a night is one continuous scale)."""
    return (hour * 60 + minute - 18 * 60) % 1440


def bedtime_drift(bedtimes: list[int]) -> int | None:
    """Population standard deviation of bedtimes, in minutes. Needs at least two nights."""
    if len(bedtimes) < 2:
        return None
    mean = sum(bedtimes) / len(bedtimes)
    return round((sum((b - mean) ** 2 for b in bedtimes) / len(bedtimes)) ** 0.5)


def pct_change(current: float | None, previous: float | None) -> float | None:
    """Difference in percentage points (0.05 is +5 points); `None` when either side is missing."""
    if current is None or previous is None:
        return None
    return round(current - previous, 4)


__all__ = ["row_status", "distribution_days", "per_day_minutes", "pace_expected", "prorate", "timedelta", "coverage", "adherence",
           "bedtime_minutes_after_18", "bedtime_drift", "pct_change"]
