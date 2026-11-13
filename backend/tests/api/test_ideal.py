import pytest
from sqlalchemy import text

from tests.factories import log, signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"


def day_body(p, effective_from="2025-01-01", **minutes):
    """A valid 24h day on Work / Personal / Sleep children. Override minutes by category name; the rest is rebalanced into Entertainment."""
    base = {"Sleep": 480, "Deep work": 480, "Meetings": 60, "Family & friends": 120, "Meals & chores": 120, "Commute": 60, "Entertainment": 120}
    base.update(minutes)
    base["Entertainment"] += 1440 - sum(base.values())
    return {"effective_from": effective_from, "allocations": [{"category_id": p.cats[n], "minutes": m} for n, m in base.items() if m > 0]}


def week_body(p, effective_from="2025-06-02"):
    rows = [("Sleep", 3360, "all_days"), ("Deep work", 1200, "weekdays"), ("Meetings", 300, "weekdays"), ("Family & friends", 1500, "all_days"),
            ("Meals & chores", 900, "all_days"), ("Commute", 300, "weekdays"), ("Entertainment", 2520, "all_days")]
    total = sum(m for _, m, _ in rows)
    rows[-1] = (rows[-1][0], rows[-1][1] + 10080 - total, rows[-1][2])
    return {"effective_from": effective_from, "allocations": [{"category_id": p.cats[n], "minutes": m, "distribution": d} for n, m, d in rows]}


async def test_seeded_ideal_day_is_returned_with_versions_and_totals(client):
    p = await signup(client)
    d = (await client.get(f"{API}/ideal/day", headers=p.headers)).json()["data"]
    assert d["current"]["total_minutes"] == 1440 and d["current"]["unallocated_minutes"] == 0 and d["current"]["expected_minutes"] == 1440
    assert [a["root_kind"] for a in d["current"]["allocations"]][0] == "work" and d["current"]["allocations"][-1]["name"] == "Sleep"
    assert len(d["versions"]) == 1 and d["versions"][0]["total_minutes"] == 1440
    w = (await client.get(f"{API}/ideal/week", headers=p.headers)).json()["data"]
    assert w["current"] is None and w["versions"] == []
    assert (await client.get(f"{API}/ideal/day?on=2020-01-01", headers=p.headers)).json()["data"]["current"] is None  # before it took effect


async def test_ac050_total_mismatch_reports_expected_actual_and_delta(client):
    p = await signup(client)
    body = day_body(p)
    body["allocations"][0]["minutes"] -= 60
    r = await client.put(f"{API}/ideal/day", headers=p.headers, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ALLOCATION_TOTAL_MISMATCH"
    assert r.json()["error"]["details"] == {"expected": 1440, "actual": 1380, "delta": -60}
    over = day_body(p); over["allocations"][0]["minutes"] += 30
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=over)).json()["error"]["details"]["delta"] == 30
    empty = await client.put(f"{API}/ideal/day", headers=p.headers, json={"effective_from": "2025-01-01", "allocations": []})
    assert empty.json()["error"]["details"] == {"expected": 1440, "actual": 0, "delta": -1440}


async def test_ac051_ancestor_and_descendant_cannot_both_be_allocated(client):
    p = await signup(client)
    body = {"effective_from": "2025-01-01", "allocations": [
        {"category_id": p.cats["Work"], "minutes": 480}, {"category_id": p.cats["Deep work"], "minutes": 480}, {"category_id": p.cats["Sleep"], "minutes": 480}]}
    r = await client.put(f"{API}/ideal/day", headers=p.headers, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ALLOCATION_NOT_ANTICHAIN"
    assert r.json()["error"]["details"] == {"ancestor_id": p.cats["Work"], "descendant_id": p.cats["Deep work"]}
    roots_only = {"effective_from": "2025-01-01", "allocations": [{"category_id": p.cats["Work"], "minutes": 540}, {"category_id": p.cats["Personal"], "minutes": 480}, {"category_id": p.cats["Sleep"], "minutes": 420}]}
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=roots_only)).status_code == 200  # roots alone are a valid antichain


async def test_input_validation_codes(client):
    p = await signup(client)
    for minutes in (0, -30, 7, 1445):
        b = day_body(p); b["allocations"][0]["minutes"] = minutes
        r = await client.put(f"{API}/ideal/day", headers=p.headers, json=b)
        assert r.json()["error"]["code"] == "INVALID_MINUTES", minutes
    dup = day_body(p); dup["allocations"].append(dict(dup["allocations"][0]))
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=dup)).json()["error"]["code"] == "DUPLICATE_ALLOCATION"
    await client.patch(f"{API}/categories/{p.cats['Sales & clients']}", headers=p.headers, json={"archived": True})
    arch = day_body(p, **{"Entertainment": 60}); arch["allocations"].append({"category_id": p.cats["Sales & clients"], "minutes": 60}); arch["allocations"][0]["minutes"] -= 60
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=arch)).json()["error"]["code"] == "CATEGORY_ARCHIVED"
    unknown = day_body(p); unknown["allocations"][0]["category_id"] = "00000000-0000-0000-0000-000000000000"
    r = await client.put(f"{API}/ideal/day", headers=p.headers, json=unknown)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    other = await signup(client)  # someone else's category looks unknown
    foreign = day_body(p); foreign["allocations"][0]["category_id"] = other.cats["Deep work"]
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=foreign)).status_code == 422


async def test_dry_run_validates_without_saving(client, db):
    p = await signup(client)
    before = (await db.execute(text("SELECT count(*) FROM ideal_templates"))).scalar_one()
    r = await client.put(f"{API}/ideal/day?dry_run=true", headers=p.headers, json=day_body(p, effective_from="2025-03-01"))
    assert r.status_code == 200 and r.json()["data"]["total_minutes"] == 1440 and r.json()["data"]["effective_from"] == "2025-03-01"
    assert (await db.execute(text("SELECT count(*) FROM ideal_templates"))).scalar_one() == before


async def test_saving_creates_versions_and_the_same_date_replaces(client):
    p = await signup(client)
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))).status_code == 200
    assert (await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-06-02", **{"Deep work": 540}))).status_code == 200
    again = await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-06-02", **{"Deep work": 600}))
    assert again.status_code == 200
    d = (await client.get(f"{API}/ideal/day?on=2025-07-01", headers=p.headers)).json()["data"]
    assert [v["effective_from"] for v in d["versions"]] == ["2026-11-13", "2025-06-02", "2025-01-01"]  # newest first, two saves on 06-02 collapsed to one
    deep = next(a for a in d["current"]["allocations"] if a["name"] == "Deep work")
    assert d["current"]["effective_from"] == "2025-06-02" and deep["minutes"] == 600
    early = (await client.get(f"{API}/ideal/day?on=2025-03-01", headers=p.headers)).json()["data"]["current"]
    assert early["effective_from"] == "2025-01-01" and next(a for a in early["allocations"] if a["name"] == "Deep work")["minutes"] == 480


async def test_ac054_week_template_totals_168h_with_distribution_and_tag_goal_outside(client):
    p = await signup(client)
    tags = (await client.get(f"{API}/tags", headers=p.headers)).json()["data"]
    assert next(t for t in tags if t["name"] == "social-media")["goal_kind"] == "max"  # a cap exists and is not part of the 10080
    r = await client.put(f"{API}/ideal/week", headers=p.headers, json=week_body(p))
    assert r.status_code == 200, r.text
    w = r.json()["data"]
    assert w["total_minutes"] == 10080 and w["unallocated_minutes"] == 0
    deep = next(a for a in w["allocations"] if a["name"] == "Deep work")
    assert deep["distribution"] == "weekdays" and deep["per_day_minutes"] == 240
    bad = week_body(p); bad["allocations"][0]["minutes"] -= 60
    r = await client.put(f"{API}/ideal/week", headers=p.headers, json=bad)
    assert r.json()["error"]["details"] == {"expected": 10080, "actual": 10020, "delta": -60}
    day_forced = day_body(p); day_forced["allocations"][0]["distribution"] = "weekdays"
    saved = (await client.put(f"{API}/ideal/day", headers=p.headers, json=day_forced)).json()["data"]
    assert {a["distribution"] for a in saved["allocations"]} == {"all_days"}  # a day template is always all_days


async def test_day_progress_compares_actual_to_target_with_status(client):
    p = await signup(client)
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))
    await log(client, p, "Focus", "2025-06-02", "09:00", "13:00", "Deep work")           # 240 vs 480 -> under
    await log(client, p, "Standup", "2025-06-02", "13:00", "14:05", "Meetings")          # 65 vs 60 -> on_target
    await log(client, p, "Odd job", "2025-06-02", "15:00", "16:00", "Sales & clients")   # not allocated -> other
    pr = (await client.get(f"{API}/ideal/progress?scope=day&on=2025-06-02", headers=p.headers)).json()["data"]
    rows = {r["name"]: r for r in pr["rows"]}
    assert rows["Deep work"]["actual"] == 240 and rows["Deep work"]["target"] == 480 and rows["Deep work"]["delta"] == -240 and rows["Deep work"]["status"] == "under"
    assert rows["Meetings"]["delta"] == 5 and rows["Meetings"]["status"] == "on_target"
    assert pr["other_actual"] == 60 and pr["total_target"] == 1440 and pr["provisional"] is False and pr["template_effective_from"] == "2025-01-01"
    assert rows["Sleep"]["actual"] == 0 and rows["Sleep"]["status"] == "under"


async def test_progress_counts_a_whole_subtree_under_an_allocated_root(client):
    p = await signup(client)
    roots = {"effective_from": "2025-01-01", "allocations": [{"category_id": p.cats["Work"], "minutes": 600}, {"category_id": p.cats["Personal"], "minutes": 420}, {"category_id": p.cats["Sleep"], "minutes": 420}]}
    await client.put(f"{API}/ideal/day", headers=p.headers, json=roots)
    await log(client, p, "A", "2025-06-02", "09:00", "10:00", "Deep work")
    await log(client, p, "B", "2025-06-02", "10:00", "11:30", "Meetings")
    await log(client, p, "C", "2025-06-02", "12:00", "13:00", "Health")
    rows = {r["name"]: r["actual"] for r in (await client.get(f"{API}/ideal/progress?scope=day&on=2025-06-02", headers=p.headers)).json()["data"]["rows"]}
    assert rows == {"Work": 150, "Personal": 60, "Sleep": 0}


async def test_ac053_a_new_version_does_not_rewrite_how_last_week_compared(client):
    p = await signup(client)
    await client.put(f"{API}/ideal/week", headers=p.headers, json=week_body(p, "2025-06-02"))
    v2 = week_body(p, "2025-06-09")
    v2["allocations"][1]["minutes"] = 1500  # Deep work 25h/week from the 9th
    v2["allocations"][-1]["minutes"] -= 300
    assert (await client.put(f"{API}/ideal/week", headers=p.headers, json=v2)).status_code == 200
    await log(client, p, "Focus", "2025-06-03", "09:00", "12:00", "Deep work")
    last = (await client.get(f"{API}/ideal/progress?scope=week&on=2025-06-08", headers=p.headers)).json()["data"]  # Sunday of the first week
    nxt = (await client.get(f"{API}/ideal/progress?scope=week&on=2025-06-09", headers=p.headers)).json()["data"]
    assert last["from_date"] == "2025-06-02" and last["template_effective_from"] == "2025-06-02"
    assert nxt["from_date"] == "2025-06-09" and nxt["template_effective_from"] == "2025-06-09"
    deep_last = next(r for r in last["rows"] if r["name"] == "Deep work")
    deep_next = next(r for r in nxt["rows"] if r["name"] == "Deep work")
    assert deep_last["target"] == 1200 and deep_next["target"] == 1500
    assert deep_last["actual"] == 180 and deep_last["expected_to_date"] == 1200 and deep_last["status"] == "under"  # a finished week owes the full target
    assert deep_next["actual"] == 0 and deep_next["expected_to_date"] == 1500


async def test_week_progress_to_date_for_the_current_week_uses_the_distribution(client):
    from datetime import UTC, datetime, timedelta

    p = await signup(client, tz="UTC")
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.isoweekday() - 1)
    await client.put(f"{API}/ideal/week", headers=p.headers, json=week_body(p, (monday - timedelta(days=7)).isoformat()))
    pr = (await client.get(f"{API}/ideal/progress?scope=week", headers=p.headers)).json()["data"]
    assert pr["provisional"] is True and pr["from_date"] == monday.isoformat()
    deep = next(r for r in pr["rows"] if r["name"] == "Deep work")
    weekdays_elapsed = min(today.isoweekday(), 5)
    assert deep["expected_to_date"] == round(1200 * weekdays_elapsed / 5)
    sleep = next(r for r in pr["rows"] if r["name"] == "Sleep")
    assert sleep["expected_to_date"] == round(3360 * today.isoweekday() / 7)


async def test_ideal_endpoints_are_scoped_to_the_user(client):
    a, b = await signup(client), await signup(client)
    await client.put(f"{API}/ideal/week", headers=a.headers, json=week_body(a))
    assert (await client.get(f"{API}/ideal/week", headers=b.headers)).json()["data"]["versions"] == []
    assert (await client.get(f"{API}/ideal/progress?scope=week&on=2025-06-03", headers=b.headers)).json()["data"]["rows"] == []
    assert (await client.get(f"{API}/ideal/day")).status_code == 401
