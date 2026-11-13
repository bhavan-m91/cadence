from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.ai.time_resolver import ItemIn, Spoken, resolve_day
from app.core.time import parse_local

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 13)


def at(h, m=0, d=DAY, tz=IST):
    return parse_local(d, time(h, m), tz)


def local(res_dt, tz=IST):
    return res_dt.astimezone(tz).strftime("%H:%M")


def window(h0=9, h1=18, d0=DAY, d1=DAY):
    return at(h0, 0, d0), at(h1, 0, d1)


# The worked example from PRD section 6.5: window 9:00am-6:00pm.
def prd_example(answers=None):
    answers = answers or {}
    return [
        ItemIn("a1", "range", start=Spoken(9, 30), duration=60, approximate=True),
        ItemIn("a2", "range", start_anchor="previous_end", end=Spoken(1, 0, "pm")),
        ItemIn("a3", "range", start=Spoken(1), end=Spoken(2)),
        ItemIn("a4", "vague", duration=45, approximate=True, window_label="afternoon", answers=answers.get("a4", {})),
        ItemIn("a5", "range", start_anchor="previous_end", end=Spoken(6)),
    ]


def test_prd_worked_example_before_any_answer():
    r = {x.key: x for x in resolve_day(prd_example(), *window(), IST)}
    assert (local(r["a1"].start), local(r["a1"].end), r["a1"].duration) == ("09:30", "10:30", 60)       # 09:00 vs 21:00 -> window picks 09:30
    assert (local(r["a2"].start), local(r["a2"].end)) == ("10:30", "13:00") and r["a2"].certainty == "inferred"
    assert (local(r["a3"].start), local(r["a3"].end)) == ("13:00", "14:00")                              # "1" -> 13:00 because it must follow 13:00
    assert "meridiem_inferred" in r["a3"].flags
    a4 = r["a4"]
    assert a4.placement == "unplaced" and a4.start is None and a4.duration == 45 and a4.blockers == ["start_time"]
    assert (local(a4.window_start), local(a4.window_end)) == ("14:00", "18:00")                          # after lunch to the window end
    a5 = r["a5"]
    assert a5.placement == "unplaced" and a5.blockers == ["start_time"] and "start_unknown" in a5.flags  # end known, start blocked by a4


def test_prd_worked_example_after_answering_the_meeting_start():
    r = {x.key: x for x in resolve_day(prd_example({"a4": {"start": "14:00"}}), *window(), IST)}
    assert (local(r["a4"].start), local(r["a4"].end), r["a4"].placement) == ("14:00", "14:45", "placed")
    assert r["a4"].certainty == "stated"                                                                  # stated by the user's answer
    a5 = r["a5"]
    assert (local(a5.start), local(a5.end), a5.duration) == ("14:45", "18:00", 195)                       # "6" -> 18:00 because 06:00 precedes the start
    assert a5.certainty == "inferred" and a5.blockers == []


def test_ac015_vague_time_with_no_duration_is_unplaced_and_asks_for_a_duration():
    items = [ItemIn("a1", "vague", window_label="afternoon")]
    r = resolve_day(items, *window(0, 24 - 0, DAY, DAY + timedelta(days=0)) if False else (at(0), at(23, 59)), IST)[0]
    assert r.placement == "unplaced" and r.start is None and r.duration is None and r.blockers == ["duration"] and "missing_duration" in r.flags
    assert (local(r.window_start), local(r.window_end)) == ("12:00", "18:00")


def test_ac016_ten_to_one_is_10am_to_1pm_not_1am():
    items = [ItemIn("a1", "range", start=Spoken(10), end=Spoken(1))]
    r = resolve_day(items, at(0), at(17), IST)[0]
    assert (local(r.start), local(r.end), r.duration) == ("10:00", "13:00", 180)


def test_the_day_moves_forward_so_a_later_small_hour_is_pm():
    items = [ItemIn("a", "range", start=Spoken(7), end=Spoken(9)), ItemIn("b", "range", start=Spoken(6), duration=60)]
    r = resolve_day(items, at(0), at(23, 59), IST)
    assert local(r[0].start) == "07:00" and local(r[1].start) == "18:00"   # 06:00 is behind the cursor, so 18:00


def test_ambiguous_with_no_context_picks_the_earliest_after_the_cursor_and_flags_it():
    r = resolve_day([ItemIn("a", "range", start=Spoken(9, 30), duration=30)], at(0), at(23, 59), IST)[0]
    assert local(r.start) == "09:30" and "meridiem_inferred" in r.flags and r.blockers == []


def test_a_big_jump_after_the_previous_activity_becomes_a_meridiem_question():
    prev = ItemIn("a", "range", start=Spoken(12, 10, "am"), end=Spoken(12, 30, "am"))
    b = ItemIn("b", "range", start=Spoken(8), duration=30)       # 08:00 is 7.5h after 00:30, 20:00 is 19.5h: ambiguous and a big jump
    assert resolve_day([prev, b], at(0), at(23, 59), IST)[1].blockers == ["meridiem"]
    b2 = ItemIn("b", "range", start=Spoken(8), duration=30, answers={"meridiem": "pm"})
    r = resolve_day([prev, b2], at(0), at(23, 59), IST)[1]
    assert local(r.start) == "20:00" and r.blockers == []
    near = ItemIn("b", "range", start=Spoken(2), duration=30)    # 02:00 is only 1.5h later: no question
    assert resolve_day([prev, near], at(0), at(23, 59), IST)[1].blockers == []


def test_label_breaks_a_tie():
    items = [ItemIn("a", "range", start=Spoken(8), duration=30, window_label="evening")]
    assert local(resolve_day(items, at(0), at(23, 59), IST)[0].start) == "20:00"


def test_midnight_crossing_sleep_with_a_window_that_starts_the_previous_evening():
    w0, w1 = at(22, 0, DAY - timedelta(days=1)), at(12, 0)
    r = resolve_day([ItemIn("s", "range", start=Spoken(11, 0, "pm"), end=Spoken(6, 30, "am"))], w0, w1, IST)[0]
    assert r.start == at(23, 0, DAY - timedelta(days=1)) and r.end == at(6, 30) and r.duration == 450


def test_sleep_that_began_before_the_window_is_carried_over_not_dropped():
    r = resolve_day([ItemIn("s", "range", start=Spoken(11, 0, "pm"), end=Spoken(7, 0, "am"))], at(0), at(12), IST)[0]
    assert r.placement == "placed" and r.start == at(23, 0, DAY - timedelta(days=1)) and r.duration == 480
    assert "outside_window" in r.flags


def test_duration_only_after_a_known_end_starts_there_when_anchored():
    items = [ItemIn("a", "range", start=Spoken(9), end=Spoken(10)), ItemIn("b", "duration", start_anchor="previous_end", duration=30)]
    r = resolve_day(items, at(0), at(23, 59), IST)
    assert (local(r[1].start), local(r[1].end)) == ("10:00", "10:30") and r[1].certainty == "inferred"


def test_duration_without_an_anchor_is_never_placed():
    items = [ItemIn("a", "range", start=Spoken(9), end=Spoken(10)), ItemIn("b", "duration", duration=30)]
    r = resolve_day(items, at(0), at(23, 59), IST)[1]
    assert r.placement == "unplaced" and r.blockers == ["start_time"] and r.duration == 30


def test_end_anchor_uses_the_next_stated_start():
    items = [ItemIn("a", "range", start=Spoken(9), end_anchor="next_start"), ItemIn("b", "range", start=Spoken(11), end=Spoken(12))]
    r = resolve_day(items, at(0), at(23, 59), IST)
    assert (local(r[0].start), local(r[0].end)) == ("09:00", "11:00") and r[0].certainty == "inferred"


def test_a_start_with_nothing_else_asks_for_a_duration_and_invents_nothing():
    r = resolve_day([ItemIn("a", "point", start=Spoken(3, 0, "pm"))], at(0), at(23, 59), IST)[0]
    assert r.placement == "unplaced" and r.blockers == ["duration"] and r.end is None and r.duration is None


def test_stated_duration_and_an_estimate_chip():
    r = resolve_day([ItemIn("a", "vague", window_label="evening", answers={"duration": 30, "duration_estimated": True, "start": "19:00"})], at(0), at(23, 59), IST)[0]
    assert (local(r.start), local(r.end), r.certainty) == ("19:00", "19:30", "estimated")


def test_end_before_start_is_repaired_with_plus_12h_then_flagged():
    r = resolve_day([ItemIn("a", "range", start=Spoken(9, 0, "pm"), end=Spoken(10, 0, "am"))], at(0), at(23, 59), IST)[0]
    assert r.placement == "placed" and r.duration == 780 and "extends_past_window" in r.flags  # 21:00 -> 10:00 next day


def test_an_activity_may_end_after_the_window():
    r = resolve_day([ItemIn("a", "range", start=Spoken(4, 0, "pm"), end=Spoken(7, 0, "pm"))], at(9), at(17), IST)[0]
    assert r.duration == 180 and "extends_past_window" in r.flags


def test_dst_fall_back_day_duration_is_real_elapsed_time():
    ny = ZoneInfo("America/New_York")
    d = date(2026, 11, 1)
    w0, w1 = parse_local(d, time(0, 0), ny), parse_local(d + timedelta(days=1), time(0, 0), ny)
    r = resolve_day([ItemIn("a", "range", start=Spoken(12, 0, "am"), end=Spoken(6, 0, "am"))], w0, w1, ny)[0]
    assert r.duration == 7 * 60  # one extra hour on the fall-back night


def test_answers_for_the_same_input_are_deterministic():
    one = resolve_day(prd_example({"a4": {"start": "14:00"}}), *window(), IST)
    two = resolve_day(prd_example({"a4": {"start": "14:00"}}), *window(), IST)
    assert one == two


__all__ = ["datetime", "timezone"]
