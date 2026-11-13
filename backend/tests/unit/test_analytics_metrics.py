from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.analytics import insights, metrics, sleep

IST = ZoneInfo("Asia/Kolkata")


def test_ac061_adherence_is_the_sum_of_capped_actuals_over_the_sum_of_targets():
    # non-sleep targets total 960; actuals matching 780 of them -> 81.25%
    assert metrics.adherence([(300, 300), (180, 240), (150, 150), (150, 270)]) == 0.8125
    assert metrics.adherence([(400, 300)]) == 1.0  # surplus never buys back a shortfall elsewhere
    assert metrics.adherence([(100, 0)]) is None  # nothing to hold you to


def test_coverage_of_a_day_that_has_not_started_is_not_a_shortfall():
    assert metrics.coverage(0, 0) == 1.0
    assert metrics.coverage(1290, 1440) == 0.8958
    assert metrics.coverage(1500, 1440) == 1.0


def test_bedtime_is_one_scale_across_midnight_and_drift_is_a_population_deviation():
    assert metrics.bedtime_minutes_after_18(23, 30) == 330
    assert metrics.bedtime_minutes_after_18(1, 0) == 420
    assert metrics.bedtime_drift([330]) is None
    assert metrics.bedtime_drift([330, 330, 330]) == 0
    assert metrics.bedtime_drift([300, 360]) == 30


def test_ac063_sleep_counts_on_the_wake_date_and_duration_only_sleep_has_no_bed_time():
    tue = date(2025, 6, 3)
    night = sleep.SleepActivity(480, True, datetime(2025, 6, 2, 23, 0, tzinfo=IST), datetime(2025, 6, 3, 7, 0, tzinfo=IST), date(2025, 6, 2))
    nap = sleep.SleepActivity(30, False, None, None, tue)
    nights = sleep.attribute([night, nap], IST)
    assert list(nights) == [tue] and nights[tue].minutes == 510 and nights[tue].bed_at is not None
    summary = sleep.summarize(nights, [date(2025, 6, 2), tue], IST, 420)
    assert summary["avg_minutes"] == 510 and summary["short_nights"] == 0 and summary["drift_minutes"] is None


def test_banners_are_capped_at_three_and_ordered_by_priority():
    rows = [{"category_id": "a", "name": "Meetings", "delta": 150}, {"category_id": "b", "name": "Learning", "delta": -200}]
    found = [insights.coverage_banner(date(2025, 6, 4), 1290, 1440), insights.tag_cap_banner("social-media", "t", 400, 300), *insights.ideal_banners(rows, "week"), insights.sleep_banner(3)]
    picked = insights.pick(found)
    assert [b.kind for b in picked] == ["coverage", "tag_cap", "ideal"]
    assert picked[0].text == "Wed 4 Jun adds up to 21h 30m, not 24h."
    assert insights.ideal_banners([{"category_id": "a", "name": "X", "delta": 20}], "week") == []  # under the 2h weekly floor
    assert len(insights.ideal_banners([{"category_id": "a", "name": "X", "delta": 40}], "day")) == 1  # over the 30m daily floor
