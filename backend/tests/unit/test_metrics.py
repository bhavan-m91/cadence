from datetime import date

from app.analytics.metrics import pace_expected, per_day_minutes, prorate, row_status
from app.core.time import date_range
from app.models.enums import IdealDistribution as D

WEEK = date_range(date(2026, 11, 9), date(2026, 11, 15))  # Mon..Sun


def test_ac055_row_status_tolerance():
    assert row_status(-12, 180) == "on_target"          # |delta| 12 <= max(15, 18)
    assert row_status(15, 60) == "on_target"            # floor of 15 minutes
    assert row_status(19, 180) == "over" and row_status(-19, 180) == "under"
    assert row_status(-16, 60) == "under"               # 10% of 60 is 6, floor 15, 16 is outside


def test_ac052_weekday_pace_is_720_by_wednesday_end():
    assert pace_expected(1200, D.weekdays, WEEK, date(2026, 11, 11)) == 720
    assert pace_expected(1200, D.weekdays, WEEK, date(2026, 11, 13)) == 1200   # Friday end: all of it
    assert pace_expected(1200, D.weekdays, WEEK, date(2026, 11, 15)) == 1200   # weekend adds nothing
    assert pace_expected(1200, D.weekdays, WEEK, date(2026, 11, 8)) == 0       # before the week starts


def test_other_distributions():
    assert pace_expected(700, D.all_days, WEEK, date(2026, 11, 11)) == 300     # 3 of 7 days
    assert pace_expected(600, D.weekend, WEEK, date(2026, 11, 14)) == 300      # Saturday of 2
    assert pace_expected(600, D.weekend, WEEK, date(2026, 11, 13)) == 0
    assert per_day_minutes(1200, D.weekdays) == 240 and per_day_minutes(700, D.all_days) == 100 and per_day_minutes(600, D.weekend) == 300


def test_prorate_today():
    assert prorate(480, 720, 1440) == 240
    assert prorate(480, 5000, 1440) == 480 and prorate(480, -5, 1440) == 0
