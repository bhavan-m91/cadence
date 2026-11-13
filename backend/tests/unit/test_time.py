from datetime import date, time

import pytest

from app.core.errors import AppError
from app.core.security import hash_password, hash_token, validate_password_strength, verify_password
from app.core.time import compute_slices, day_bounds, elapsed_minutes, get_zone, parse_local, week_start_date
from tests.factories import utc

NY = get_zone("America/New_York")
IST = get_zone("Asia/Kolkata")


def test_day_length_on_dst_days():
    assert elapsed_minutes(date(2026, 3, 8), NY) == 23 * 60  # spring forward
    assert elapsed_minutes(date(2026, 11, 1), NY) == 25 * 60  # fall back
    assert elapsed_minutes(date(2026, 6, 1), NY) == 24 * 60
    assert elapsed_minutes(date(2026, 3, 8), IST) == 24 * 60


def test_slice_inside_one_day():
    s = compute_slices(utc(2025, 6, 2, 4, 0), utc(2025, 6, 2, 7, 30), IST)
    assert [(x.local_date, x.minutes) for x in s] == [(date(2025, 6, 2), 210)]


def test_sleep_crossing_midnight_is_split_by_local_day():
    # 23:00 -> 07:00 IST = 17:30Z -> 01:30Z next day
    s = compute_slices(utc(2025, 6, 2, 17, 30), utc(2025, 6, 3, 1, 30), IST)
    assert [(x.local_date, x.minutes) for x in s] == [(date(2025, 6, 2), 60), (date(2025, 6, 3), 420)]
    assert sum(x.minutes for x in s) == 480


def test_fall_back_hour_counts_real_elapsed_minutes():
    # 01:30 EDT -> 01:30 EST: the wall clock does not move but 60 real minutes pass
    s = compute_slices(utc(2026, 11, 1, 5, 30), utc(2026, 11, 1, 6, 30), NY)
    assert sum(x.minutes for x in s) == 60


def test_full_dst_day_slices_sum_to_real_day_length():
    for d, expected in ((date(2026, 3, 8), 1380), (date(2026, 11, 1), 1500)):
        start, end = day_bounds(d, NY)
        s = compute_slices(start, end, NY)
        assert [x.minutes for x in s] == [expected]


def test_slice_spanning_three_days():
    s = compute_slices(utc(2025, 6, 1, 12, 0), utc(2025, 6, 4, 12, 0), IST)
    assert sum(x.minutes for x in s) == 72 * 60
    assert len(s) == 4


def test_nonexistent_local_time_is_refused():
    with pytest.raises(AppError) as e:
        parse_local(date(2026, 3, 8), time(2, 30), NY)
    assert e.value.code == "INVALID_LOCAL_TIME"
    assert parse_local(date(2026, 3, 8), time(3, 30), NY).hour == 7  # 03:30 EDT = 07:30Z


def test_week_start():
    assert week_start_date(date(2026, 11, 13), 1) == date(2026, 11, 9)  # Friday -> Monday
    assert week_start_date(date(2026, 11, 13), 7) == date(2026, 11, 8)  # Sunday start
    assert week_start_date(date(2026, 11, 9), 1) == date(2026, 11, 9)


def test_password_policy_and_hashing():
    for bad in ("short", "password1234", "aaaaaaaaaaaa"):
        with pytest.raises(AppError) as e:
            validate_password_strength(bad)
        assert e.value.code == "WEAK_PASSWORD"
    validate_password_strength("correct horse battery")
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2id$") and verify_password("correct horse battery", h) and not verify_password("nope", h)
    assert not verify_password("x", None)
    assert len(hash_token("abc")) == 64
