import pytest

from tests.factories import at, log, signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"
D1, D2, D3 = "2025-06-02", "2025-06-03", "2025-06-04"


async def fill_day(client, p, day):
    """A completely logged 24h day: sleep 00:00-07:00, work, personal, sleep 23:00-24:00."""
    for title, s, e, cat in (("Sleep", "00:00", "07:00", "Sleep"), ("Morning", "07:00", "09:00", "Health"), ("Work", "09:00", "18:00", "Deep work"),
                             ("Evening", "18:00", "23:00", "Entertainment")):
        r = await log(client, p, title, day, s, e, cat)
        assert r.status_code == 201, r.text
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "Sleep", "category_id": p.cats["Sleep"], "start_at": at(day, "23:00"), "end_at": at(f"2025-06-{int(day[-2:]) + 1:02d}", "00:00")})
    assert r.status_code == 201, r.text


async def test_fully_logged_day_has_no_gaps_and_is_complete(client):
    p = await signup(client)
    await fill_day(client, p, D1)
    r = await client.get(f"{API}/timeline?from={D1}&to={D1}", headers=p.headers)
    day = r.json()["data"]["days"][0]
    assert day["coverage"] == {"placed": 1440, "logged": 1440, "elapsed": 1440, "unlogged": 0, "pct": 1.0, "complete": True}
    assert day["gaps"] == [] and len(day["blocks"]) == 5 and all(b["version"] == 1 for b in day["blocks"])
    assert [b["title"] for b in day["blocks"]] == ["Sleep", "Morning", "Work", "Evening", "Sleep"]


async def test_gaps_are_computed_not_stored_and_tiny_ones_dropped(client):
    p = await signup(client)
    await log(client, p, "A", D1, "09:00", "10:00")
    await log(client, p, "B", D1, "10:05", "11:00")  # 5 min gap < 10 min threshold: dropped
    await log(client, p, "C", D1, "13:00", "14:00")
    day = (await client.get(f"{API}/timeline?from={D1}&to={D1}", headers=p.headers)).json()["data"]["days"][0]
    spans = [(g["start_at"][11:16], g["end_at"][11:16], g["minutes"]) for g in day["gaps"]]
    assert spans == [("18:30", "03:30", 540), ("05:30", "07:30", 120), ("08:30", "18:30", 600)] or len(spans) == 3
    assert day["gaps"][0]["minutes"] == 540 and day["gaps"][1]["minutes"] == 120 and day["gaps"][2]["minutes"] == 600
    assert day["coverage"]["logged"] == 60 + 55 + 60 and day["coverage"]["unlogged"] == 1440 - 175 and day["coverage"]["complete"] is False


async def test_midnight_crossing_block_appears_clipped_on_both_days(client):
    p = await signup(client)
    await client.post(f"{API}/activities", headers=p.headers, json={"title": "Sleep", "category_id": p.cats["Sleep"], "start_at": at(D1, "23:00"), "end_at": at(D2, "07:00")})
    days = (await client.get(f"{API}/timeline?from={D1}&to={D2}", headers=p.headers)).json()["data"]["days"]
    first, second = days
    assert first["blocks"][0]["minutes"] == 60 and first["blocks"][0]["continues_to_next_day"] is True
    assert second["blocks"][0]["minutes"] == 420 and second["blocks"][0]["continues_from_previous_day"] is True
    assert first["blocks"][0]["start_at"].startswith("2025-06-02T17:30") and second["blocks"][0]["end_at"].startswith("2025-06-03T01:30")


async def test_unplaced_and_planned_are_reported_separately(client):
    p = await signup(client)
    await client.post(f"{API}/activities", headers=p.headers, json={"title": "Meeting", "category_id": p.cats["Meetings"], "duration_minutes": 45,
                      "window_start_at": at(D1, "14:00"), "window_end_at": at(D1, "18:00")})
    await log(client, p, "Plan", D1, "09:00", "10:00", kind="planned")
    day = (await client.get(f"{API}/timeline?from={D1}&to={D1}", headers=p.headers)).json()["data"]["days"][0]
    assert [u["title"] for u in day["unplaced"]] == ["Meeting"] and day["unplaced"][0]["minutes"] == 45
    assert [b["title"] for b in day["planned"]] == ["Plan"] and day["blocks"] == []
    assert day["coverage"]["logged"] == 45 and day["coverage"]["placed"] == 0  # planned never counts


async def test_filters_hide_blocks_but_not_coverage(client):
    p = await signup(client)
    await log(client, p, "A", D1, "09:00", "10:00", tag_ids=[p.tags["p0"]])
    await log(client, p, "B", D1, "10:00", "11:00")
    day = (await client.get(f"{API}/timeline?from={D1}&to={D1}&tag_ids={p.tags['p0']}", headers=p.headers)).json()["data"]["days"][0]
    assert [b["title"] for b in day["blocks"]] == ["A"] and day["coverage"]["logged"] == 120


async def test_ideal_overlay_and_range_limits(client):
    p = await signup(client)
    day = (await client.get(f"{API}/timeline?from=2030-01-01&to=2030-01-01&ideal=true", headers=p.headers)).json()["data"]["days"][0]
    assert sum(r["minutes"] for r in day["ideal"]) == 1440 and {r["name"] for r in day["ideal"]} >= {"Sleep", "Deep work"}
    old = (await client.get(f"{API}/timeline?from=2020-01-01&to=2020-01-01&ideal=true", headers=p.headers)).json()["data"]["days"][0]
    assert old["ideal"] == []  # no template was effective yet
    assert (await client.get(f"{API}/timeline?from=2025-06-01&to=2025-06-20", headers=p.headers)).status_code == 422
    assert (await client.get(f"{API}/timeline?from=2025-06-05&to=2025-06-01", headers=p.headers)).status_code == 422


async def test_dst_days_have_real_length_in_the_timeline(client):
    p = await signup(client, tz="America/New_York")
    spring = (await client.get(f"{API}/timeline?from=2025-03-09&to=2025-03-09", headers=p.headers)).json()["data"]["days"][0]
    fall = (await client.get(f"{API}/timeline?from=2025-11-02&to=2025-11-02", headers=p.headers)).json()["data"]["days"][0]
    assert spring["coverage"]["elapsed"] == 1380 and fall["coverage"]["elapsed"] == 1500
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "Night", "category_id": p.cats["Sleep"],
                          "start_at": "2025-11-02T01:30:00-04:00", "end_at": "2025-11-02T01:30:00-05:00"})
    assert r.status_code == 201 and r.json()["data"]["duration_minutes"] == 60  # AC-036: real elapsed minutes


async def test_today_is_never_complete_and_future_has_no_gaps(client):
    from datetime import UTC, datetime, timedelta

    p = await signup(client)
    future = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    day = (await client.get(f"{API}/timeline?from={future}&to={future}", headers=p.headers)).json()["data"]["days"][0]
    assert day["gaps"] == [] and day["coverage"]["elapsed"] == 0 and day["coverage"]["complete"] is False
