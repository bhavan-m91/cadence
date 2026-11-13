import pytest

from app.ai.providers.fake_provider import FixtureProvider
from tests.ai_fixtures import prd_response
from tests.api.test_ideal import day_body, week_body
from tests.factories import at, create_entry, log, signup, submit

pytestmark = pytest.mark.asyncio
API = "/api/v1"
MON = "2025-06-02"  # a Monday in the past, so every day below is complete


async def get(client, p, url, **kw):
    r = await client.get(f"{API}{url}", headers={**p.headers, **kw.pop("headers", {})}, **kw)
    return r


async def day(client, p, d=MON):
    r = await get(client, p, f"/analytics/day/{d}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_ac059_category_totals_count_once_and_every_tag_gets_the_full_duration(client):
    p = await signup(client)
    await log(client, p, "Deep session", MON, "09:00", "12:00", tag_ids=[p.tags["bug"], p.tags["p0"], p.tags["meetings"]])
    d = await day(client, p)
    cats = {c["name"]: c["minutes"] for c in d["by_category"]}
    assert cats == {"Deep work": 180}
    assert {t["name"]: t["minutes"] for t in d["by_tag"]} == {"bug": 180, "p0": 180, "meetings": 180}


async def test_ac060_a_completed_day_with_21h30_placed_is_150_short_and_not_complete(client):
    p = await signup(client)
    await log(client, p, "Almost everything", MON, "00:00", "21:30")
    c = (await day(client, p))["coverage"]
    assert c["placed"] == 1290 and c["elapsed"] == 1440 and c["unlogged"] == 150 and c["complete"] is False and c["pct"] == 0.8958


async def test_a_day_within_tolerance_is_complete(client):
    p = await signup(client)
    await log(client, p, "All day", MON, "00:00", "23:55")
    assert (await day(client, p))["coverage"]["complete"] is True


async def test_ac062_today_is_provisional_and_targets_are_prorated(client, monkeypatch):
    from datetime import UTC, datetime

    from app.core import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(2025, 6, 2, 12, 30, tzinfo=UTC))  # 18:00 in Asia/Kolkata
    p = await signup(client)
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))  # the seeded one starts on the real onboarding date
    d = await day(client, p)
    assert d["ideal"]["adherence"]["provisional"] is True and d["coverage"]["elapsed"] == 1080
    deep = next(r for r in d["ideal"]["rows"] if r["name"] == "Deep work")
    assert deep["expected"] == round(deep["target"] * 0.75)
    yesterday = await day(client, p, "2025-06-01")
    assert yesterday["ideal"]["adherence"]["provisional"] is False


async def test_ac063_sleep_lands_on_the_wake_date(client):
    p = await signup(client)
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "Night", "category_id": p.cats["Sleep"], "start_at": at(MON, "23:00"), "end_at": at("2025-06-03", "07:00")})
    assert r.status_code == 201, r.text
    tue = (await day(client, p, "2025-06-03"))["sleep"]
    assert [n["date"] for n in tue["nights"]] == ["2025-06-03"] and tue["nights"][0]["minutes"] == 480 and tue["nights"][0]["short"] is False
    mon = (await day(client, p, MON))["sleep"]
    assert mon["nights"] == []  # the night belongs to Tuesday


async def test_ac064_and_ac065_drafts_and_plans_never_count(client, db):
    p = await signup(client)
    await log(client, p, "Planned block", MON, "09:00", "10:00", kind="planned")
    entry = (await create_entry(client, p, "x", day=MON)).json()["data"]
    await submit(client, db, p, entry["id"], FixtureProvider(prd_response(p)))  # drafts now exist
    d = await day(client, p)
    assert d["coverage"]["logged"] == 0 and d["by_category"] == [] and d["certainty"] == {"recorded": 0, "estimated": 0}
    week = (await get(client, p, f"/analytics/week/{MON}")).json()["data"]
    assert week["coverage"]["logged"] == 0 and week["by_tag"] == []


async def test_ac066_unchanged_data_answers_304_and_a_write_changes_the_tag(client):
    p = await signup(client)
    await log(client, p, "Work", MON, "09:00", "10:00")
    first = await get(client, p, f"/analytics/day/{MON}")
    tag = first.headers["etag"]
    again = await get(client, p, f"/analytics/day/{MON}", headers={"If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    await log(client, p, "More", MON, "10:00", "11:00")
    changed = await get(client, p, f"/analytics/day/{MON}", headers={"If-None-Match": tag})
    assert changed.status_code == 200 and changed.headers["etag"] != tag


async def test_ac067_breakdown_with_a_tag_filter_matches_the_activities_listing(client):
    p = await signup(client)
    await log(client, p, "A", MON, "09:00", "10:30", tag_ids=[p.tags["p0"]])
    await log(client, p, "B", MON, "11:00", "12:00", tag_ids=[p.tags["p0"], p.tags["bug"]])
    await log(client, p, "C", MON, "13:00", "15:00", tag_ids=[p.tags["bug"]])
    tag = p.tags["p0"]
    b = (await get(client, p, f"/analytics/breakdown?from={MON}&to={MON}&by=category&tag_ids={tag}")).json()["data"]
    listed = (await get(client, p, f"/activities?from={MON}&to={MON}&tag_ids={tag}")).json()["data"]
    assert b["total_minutes"] == sum(a["duration_minutes"] for a in listed) == 150
    assert b["series_kind"] == "partition"
    overlay = (await get(client, p, f"/analytics/breakdown?from={MON}&to={MON}&by=tag")).json()["data"]
    assert overlay["series_kind"] == "overlay" and {i["name"]: i["minutes"] for i in overlay["items"]}["bug"] == 180


async def test_category_breakdown_rolls_children_up_to_their_root(client):
    p = await signup(client)
    await log(client, p, "Build", MON, "09:00", "11:00", category="Deep work")
    await log(client, p, "Standup", MON, "11:00", "11:30", category="Meetings")
    await log(client, p, "Sleep", MON, "00:00", "07:00", category="Sleep")
    items = {i["name"]: i for i in (await get(client, p, f"/analytics/breakdown?from={MON}&to={MON}")).json()["data"]["items"]}
    assert items["Work"]["rollup_minutes"] == 150 and items["Work"]["minutes"] == 0 and items["Deep work"]["minutes"] == 120
    b = (await get(client, p, f"/analytics/breakdown?from={MON}&to={MON}")).json()["data"]
    assert b["waking_minutes"] == 150 and b["total_minutes"] == 150 + 420
    assert items["Work"]["share"] == 1.0 and items["Sleep"]["share"] == 0.0  # sleep is not part of waking time


async def test_week_adherence_uses_completed_days_only_and_flags_the_unallocated(client):
    p = await signup(client)
    assert (await client.put(f"{API}/ideal/week", headers=p.headers, json=week_body(p, MON))).status_code == 200
    for d in ("2025-06-02", "2025-06-03", "2025-06-04"):
        await log(client, p, "Focus", d, "09:00", "13:00", category="Deep work")  # 240/day against 240/day (1200 weekdays / 5)
    await log(client, p, "Reading", "2025-06-03", "14:00", "15:00", category="Learning")  # outside every allocation
    w = (await get(client, p, f"/analytics/week/{MON}")).json()["data"]
    assert w["ideal"]["kind"] == "week" and w["ideal"]["unallocated_actual"] == 60
    deep = next(r for r in w["ideal"]["rows"] if r["name"] == "Deep work")
    assert deep["actual"] == 720 and deep["expected"] == 1200 and deep["delta"] == -480
    assert [d["focus"] for d in w["days"][:3]] == [240, 300, 240]  # Learning counts as focus
    bad = await get(client, p, "/analytics/week/2025-06-03")
    assert bad.status_code == 422 and bad.json()["error"]["details"]["fields"][0]["rule"] == "not_week_start"


async def test_without_an_ideal_the_comparison_is_null_and_setup_is_flagged(client):
    p = await signup(client)
    w = (await get(client, p, f"/analytics/week/{MON}")).json()["data"]
    assert w["ideal"] is None and w["ideal_setup_needed"] is True
    assert (await day(client, p))["ideal_setup_needed"] is True  # the seeded Ideal Day only starts on the onboarding date
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))
    assert (await day(client, p))["ideal_setup_needed"] is False


async def test_overview_week_has_kpis_banners_and_deadlines(client):
    p = await signup(client)
    await log(client, p, "Short day", "2025-06-04", "09:00", "17:00")
    await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Ship it", "due_date": "2025-06-30"})
    o = (await get(client, p, f"/analytics/overview?scope=week&anchor={MON}")).json()["data"]
    assert o["range"] == {"from": MON, "to": "2025-06-08"} and o["kpis"]["logged_minutes"] == 480
    cov = [b for b in o["banners"] if b["kind"] == "coverage"]
    assert cov and cov[0]["action"]["route"] == "/calendar?date=2025-06-04" and "8h" in cov[0]["text"]
    assert len(o["banners"]) <= 3
    assert {"actual_vs_ideal", "coverage_by_day", "sleep", "focus", "work_vs_personal"} <= set(o["charts"])
    assert o["rhythm"] is None


async def test_overview_day_includes_the_rhythm_for_the_day(client):
    p = await signup(client)
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))
    await log(client, p, "Build", MON, "09:00", "11:00")
    o = (await get(client, p, f"/analytics/overview?scope=day&anchor={MON}")).json()["data"]
    assert o["rhythm"]["date"] == MON and len(o["rhythm"]["blocks"]) == 1 and o["rhythm"]["ideal"]


async def test_tag_over_its_weekly_cap_raises_a_banner(client):
    p = await signup(client)
    t = (await client.post(f"{API}/tags", headers=p.headers, json={"name": "doomscroll", "goal_kind": "max", "goal_weekly_minutes": 60})).json()["data"]
    await log(client, p, "Scrolling", MON, "20:00", "22:00", tag_ids=[t["id"]])
    o = (await get(client, p, f"/analytics/overview?scope=week&anchor={MON}")).json()["data"]
    assert any(b["kind"] == "tag_cap" and "#doomscroll" in b["text"] for b in o["banners"])
    assert next(g for g in o["charts"]["tag_goals"] if g["name"] == "doomscroll")["goal_status"] == "over"


async def test_work_outside_the_office_is_counted_separately(client):
    p = await signup(client)
    await log(client, p, "At home", MON, "09:00", "11:00", location_type="home")
    await log(client, p, "In office", MON, "11:00", "12:00", location_type="office")
    wp = (await day(client, p))["work_vs_personal"]
    assert wp["work"] == 180 and wp["work_outside_office"] == 120


async def test_trends_shape_limits_and_values(client):
    p = await signup(client)
    for d in ("2025-06-02", "2025-06-03"):
        await log(client, p, "Focus", d, "09:00", "11:00")
    r = await get(client, p, "/analytics/trends?metric=focus&granularity=week&periods=8")
    pts = r.json()["data"]["points"]
    assert len(pts) == 8 and pts[-1]["period_start"] >= pts[0]["period_start"] and r.json()["data"]["metric"] == "focus"
    assert (await get(client, p, "/analytics/trends?metric=focus&granularity=week&periods=53")).status_code == 422
    assert (await get(client, p, "/analytics/trends?metric=focus&granularity=day&periods=182")).status_code == 200
    assert (await get(client, p, "/analytics/trends?metric=bogus&granularity=day&periods=7")).status_code == 422


async def test_trend_values_for_a_known_week(client, monkeypatch):
    from datetime import UTC, datetime

    from app.core import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(2025, 6, 9, 6, 0, tzinfo=UTC))  # Monday of the following week, so 2 Jun is complete
    p = await signup(client)
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))
    await log(client, p, "Focus", MON, "09:00", "13:00")
    focus = (await get(client, p, "/analytics/trends?metric=focus&granularity=week&periods=2")).json()["data"]["points"]
    assert focus[0]["period_start"] == MON and focus[0]["value"] == 240.0
    adh = (await get(client, p, "/analytics/trends?metric=adherence&granularity=day&periods=8")).json()["data"]["points"]
    monday = next(x for x in adh if x["period_start"] == MON)
    assert monday["value"] is not None and 0 < monday["value"] < 1


async def test_nobody_sees_another_users_numbers(client):
    a, b = await signup(client), await signup(client)
    await log(client, a, "Mine", MON, "09:00", "12:00")
    assert (await day(client, a))["coverage"]["logged"] == 180
    assert (await day(client, b))["coverage"]["logged"] == 0
    assert (await get(client, b, f"/analytics/breakdown?from={MON}&to={MON}")).json()["data"]["total_minutes"] == 0


async def test_analytics_require_a_signed_in_user(client):
    assert (await client.get(f"{API}/analytics/day/{MON}")).status_code == 401


async def test_ac068_trends_over_26_weeks_and_7000_activities_stay_under_400ms_p95(client, db):
    import time
    import uuid
    from datetime import date, timedelta

    from sqlalchemy import insert

    from app.core.time import day_start, get_zone
    from app.models import Activity, ActivityDaySlice

    p = await signup(client)
    tz, cat = get_zone("Asia/Kolkata"), uuid.UUID(p.cats["Deep work"])
    acts, slices = [], []
    first = date(2025, 1, 6)
    for i in range(182):
        d = first + timedelta(days=i)
        base = day_start(d, tz)
        for j in range(38):  # 38 x 20 min = 12h40 a day, about 6,900 rows over 26 weeks
            aid = uuid.uuid4()
            start, end = base + timedelta(minutes=20 * j), base + timedelta(minutes=20 * j + 20)
            acts.append(dict(id=aid, user_id=uuid.UUID(p.id), title="Block", category_id=cat, placement="placed", start_at=start, end_at=end, duration_minutes=20,
                             timezone="Asia/Kolkata", local_date=d, status="confirmed", kind="actual", origin="manual", time_certainty="stated"))
            slices.append(dict(activity_id=aid, local_date=d, user_id=uuid.UUID(p.id), minutes=20, is_placed=True, slice_start_at=start, slice_end_at=end,
                               category_id=cat, time_certainty="stated"))
    await db.execute(insert(Activity), acts)
    await db.execute(insert(ActivityDaySlice), slices)
    await db.flush()
    times = []
    for metric in ("adherence", "coverage", "focus", "sleep"):
        for _ in range(13):
            t0 = time.perf_counter()
            r = await get(client, p, f"/analytics/trends?metric={metric}&granularity=week&periods=26")
            times.append(time.perf_counter() - t0)
            assert r.status_code == 200
    times.sort()
    assert times[int(len(times) * 0.95) - 1] < 0.4, f"p95 {times[int(len(times) * 0.95) - 1]:.3f}s over {len(times)} calls"
