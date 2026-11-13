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


__all__ = ["row_status", "distribution_days", "per_day_minutes", "pace_expected", "prorate", "timedelta"]
