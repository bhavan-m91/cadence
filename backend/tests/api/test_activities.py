import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Activity
from app.models.enums import ActivityStatus, Placement
from app.repositories.activities import ActivitiesRepository
from tests.factories import at, log, signup, utc

pytestmark = pytest.mark.asyncio
API = "/api/v1"
DAY = "2025-06-02"


async def invariants_ok(db, person) -> bool:
    import uuid

    return await ActivitiesRepository(db, uuid.UUID(person.id)).slice_invariant_violations() == []


async def test_create_placed_activity_computes_duration_slices_and_event(client, db):
    p = await signup(client)
    r = await log(client, p, "Deep work", DAY, "09:30", "11:00", description="Fixing the sync bug", tag_ids=[p.tags["bug"]], location_type="office")
    assert r.status_code == 201, r.text
    a = r.json()["data"]
    assert a["duration_minutes"] == 90 and a["placement"] == "placed" and a["status"] == "confirmed" and a["origin"] == "manual"
    assert a["local_date"] == DAY and a["start_at"].startswith("2025-06-02T04:00:00") and a["category"]["name"] == "Deep work"
    assert [t["name"] for t in a["tags"]] == ["bug"] and a["version"] == 1
    rows = (await db.execute(text("SELECT local_date, minutes, is_placed FROM activity_day_slices"))).all()
    assert [(str(d), m, pl) for d, m, pl in rows] == [(DAY, 90, True)]
    ev = (await client.get(f"{API}/activities/{a['id']}/events", headers=p.headers)).json()["data"]
    assert [e["event_type"] for e in ev] == ["created"]
    assert await invariants_ok(db, p)


async def test_seconds_are_floored_to_whole_minutes(client):
    p = await signup(client)
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "x", "category_id": p.cats["Admin"],
                          "start_at": "2025-06-02T09:00:42+05:30", "end_at": "2025-06-02T09:45:59+05:30"})
    assert r.status_code == 201 and r.json()["data"]["duration_minutes"] == 45


async def test_overlap_is_rejected_with_conflicting_ids(client):
    p = await signup(client)
    first = (await log(client, p, "Lunch", DAY, "13:00", "14:00", "Meals & chores")).json()["data"]
    r = await log(client, p, "Meeting", DAY, "13:45", "15:00", "Meetings")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "ACTIVITY_OVERLAP" and err["details"]["conflicts"] == [{"id": first["id"], "title": "Lunch", "overlap_minutes": 15}]
    assert (await log(client, p, "Back to back", DAY, "14:00", "15:00")).status_code == 201  # [start, end) is half-open


async def test_database_constraint_blocks_overlap_even_when_the_service_is_bypassed(client, db):
    p = await signup(client)
    await log(client, p, "A", DAY, "09:00", "10:00")
    with pytest.raises(IntegrityError) as e:
        await db.execute(text("""
            INSERT INTO activities (user_id, title, category_id, placement, start_at, end_at, duration_minutes, timezone, local_date)
            SELECT user_id, 'sneaky', category_id, 'placed', start_at + interval '30 minutes', end_at + interval '30 minutes', 60, timezone, local_date
            FROM activities LIMIT 1"""))
    assert "activities_no_overlap" in str(e.value)


async def test_planned_and_draft_and_deleted_activities_do_not_collide_with_actuals(client):
    p = await signup(client)
    await log(client, p, "Actual", DAY, "09:00", "10:00")
    plan = await log(client, p, "Planned", DAY, "09:30", "10:30", kind="planned")
    assert plan.status_code == 201
    done = await client.post(f"{API}/activities/{plan.json()['data']['id']}/mark-done", headers=p.headers, json={})
    assert done.status_code == 409 and done.json()["error"]["code"] == "ACTIVITY_OVERLAP"
    ok = await client.post(f"{API}/activities/{plan.json()['data']['id']}/mark-done", headers=p.headers, json={"start_at": at(DAY, "10:00"), "end_at": at(DAY, "11:00")})
    assert ok.status_code == 200 and ok.json()["data"]["kind"] == "actual"
    again = await client.post(f"{API}/activities/{plan.json()['data']['id']}/mark-done", headers=p.headers, json={})
    assert again.status_code == 422 and again.json()["error"]["code"] == "NOT_PLANNED"


async def test_unplaced_activity_uses_window_and_counts_toward_totals(client, db):
    p = await signup(client)
    r = await client.post(f"{API}/activities", headers=p.headers, json={
        "title": "Meeting", "category_id": p.cats["Meetings"], "duration_minutes": 45, "time_certainty": "estimated",
        "window_start_at": at(DAY, "14:00"), "window_end_at": at(DAY, "18:00")})
    assert r.status_code == 201 and r.json()["data"]["placement"] == "unplaced" and r.json()["data"]["start_at"] is None
    rows = (await db.execute(text("SELECT minutes, is_placed FROM activity_day_slices"))).all()
    assert rows == [(45, False)]
    too_long = await client.post(f"{API}/activities", headers=p.headers, json={
        "title": "x", "category_id": p.cats["Meetings"], "duration_minutes": 300, "window_start_at": at(DAY, "14:00"), "window_end_at": at(DAY, "16:00")})
    assert too_long.status_code == 422 and too_long.json()["error"]["code"] == "DURATION_EXCEEDS_WINDOW"
    assert (await invariants_ok(db, p))


async def test_validation_rules(client):
    p = await signup(client)
    base = {"title": "x", "category_id": p.cats["Admin"]}
    assert (await client.post(f"{API}/activities", headers=p.headers, json={**base, "start_at": at(DAY, "10:00")})).status_code == 422
    assert (await client.post(f"{API}/activities", headers=p.headers, json={**base, "start_at": at(DAY, "10:00"), "end_at": at(DAY, "09:00")})).status_code == 422
    too_long = await client.post(f"{API}/activities", headers=p.headers, json={**base, "start_at": "2025-06-02T00:00:00+05:30", "end_at": "2025-06-03T01:00:00+05:30"})
    assert too_long.status_code == 422 and too_long.json()["error"]["code"] == "DURATION_TOO_LONG"
    assert (await client.post(f"{API}/activities", headers=p.headers, json={**base, "title": "  ", "start_at": at(DAY, "09:00"), "end_at": at(DAY, "10:00")})).status_code == 422
    unknown_cat = {**base, "category_id": "00000000-0000-0000-0000-000000000000", "start_at": at(DAY, "09:00"), "end_at": at(DAY, "10:00")}
    assert (await client.post(f"{API}/activities", headers=p.headers, json=unknown_cat)).status_code == 422


async def test_ac032_optimistic_lock_second_writer_gets_409(client):
    p = await signup(client)
    a = (await log(client, p, "Work", DAY, "09:00", "10:00")).json()["data"]
    one = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 1, "title": "First"})
    assert one.status_code == 200 and one.json()["data"]["version"] == 2 and one.json()["data"]["user_edited"] is True
    two = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 1, "title": "Second"})
    assert two.status_code == 409 and two.json()["error"]["code"] == "VERSION_CONFLICT" and two.json()["error"]["details"]["current_version"] == 2


async def test_ac030_resize_into_neighbour_is_refused_and_original_survives(client):
    p = await signup(client)
    a = (await log(client, p, "A", DAY, "09:00", "10:00")).json()["data"]
    await log(client, p, "B", DAY, "10:00", "11:00")
    r = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 1, "end_at": at(DAY, "10:30")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVITY_OVERLAP"
    still = (await client.get(f"{API}/activities/{a['id']}", headers=p.headers)).json()["data"]
    assert still["duration_minutes"] == 60 and still["version"] == 1


async def test_patch_time_category_task_and_clear(client, db):
    p = await signup(client)
    a = (await log(client, p, "Work", DAY, "09:00", "10:00")).json()["data"]
    r = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 1, "end_at": at(DAY, "10:30"), "category_id": p.cats["Meetings"], "location_type": "home"})
    d = r.json()["data"]
    assert d["duration_minutes"] == 90 and d["category"]["name"] == "Meetings" and d["location_type"] == "home"
    r = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 2, "duration_minutes": 30})
    assert r.json()["data"]["duration_minutes"] == 30 and r.json()["data"]["end_at"].startswith("2025-06-02T04:00")
    r = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 3, "clear": ["location_type"]})
    assert r.json()["data"]["location_type"] is None
    cat_in_slice = (await db.execute(text("SELECT category_id::text FROM activity_day_slices"))).scalar_one()
    assert cat_in_slice == p.cats["Meetings"]
    assert await invariants_ok(db, p)
    ev = [e["event_type"] for e in (await client.get(f"{API}/activities/{a['id']}/events", headers=p.headers)).json()["data"]]
    assert ev == ["created", "edited", "edited", "edited"]


async def test_task_link_inherits_project_until_overridden(client):
    p = await signup(client)
    proj = (await client.post(f"{API}/projects", headers=p.headers, json={"name": "Product B"})).json()["data"]
    task = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Fix sync", "project_id": proj["id"]})).json()["data"]
    a = (await log(client, p, "Work", DAY, "09:00", "10:00")).json()["data"]
    r = await client.patch(f"{API}/activities/{a['id']}", headers=p.headers, json={"version": 1, "task_id": task["id"]})
    assert r.json()["data"]["project_id"] == proj["id"] and r.json()["data"]["task_id"] == task["id"]
    detail = (await client.get(f"{API}/activities/{a['id']}", headers=p.headers)).json()["data"]
    assert detail["task"]["title"] == "Fix sync"


async def test_ac028_split(client, db):
    p = await signup(client)
    a = (await log(client, p, "Deep work", "2025-06-02", "10:00", "13:00", tag_ids=[p.tags["p0"], p.tags["bug"]])).json()["data"]
    r = await client.post(f"{API}/activities/{a['id']}/split", headers=p.headers, json={"at": at(DAY, "11:30")})
    assert r.status_code == 200
    orig, new = r.json()["data"]["original"], r.json()["data"]["created"]
    assert orig["duration_minutes"] == new["duration_minutes"] == 90 and orig["end_at"] == new["start_at"]
    assert sorted(t["name"] for t in orig["tags"]) == sorted(t["name"] for t in new["tags"]) == ["bug", "p0"]
    assert new["derived_from_id"] == orig["id"] and new["origin"] == "split" and new["category"]["name"] == "Deep work"
    assert await invariants_ok(db, p)
    for bad in ("10:03", "12:58", "09:00", "14:00"):
        again = await client.post(f"{API}/activities/{new['id']}/split", headers=p.headers, json={"at": at(DAY, bad)})
        assert again.status_code == 422 and again.json()["error"]["code"] == "SPLIT_POINT_INVALID"


async def test_ac029_merge_contiguous_blocks_unions_tags(client, db):
    p = await signup(client)
    a = (await log(client, p, "Part 1", DAY, "09:00", "10:00", tag_ids=[p.tags["bug"]])).json()["data"]
    b = (await log(client, p, "Part 2", DAY, "10:00", "11:00", tag_ids=[p.tags["p0"]])).json()["data"]
    r = await client.post(f"{API}/activities/merge", headers=p.headers, json={"activity_ids": [b["id"], a["id"]], "title": "Whole block"})
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["id"] == a["id"] and m["duration_minutes"] == 120 and m["title"] == "Whole block" and m["origin"] == "merge"
    assert sorted(t["name"] for t in m["tags"]) == ["bug", "p0"]
    assert (await client.get(f"{API}/activities/{b['id']}", headers=p.headers)).status_code == 404
    assert (await db.execute(text("SELECT sum(minutes) FROM activity_day_slices"))).scalar_one() == 120
    assert await invariants_ok(db, p)


async def test_merge_rules(client):
    p = await signup(client)
    a = (await log(client, p, "A", DAY, "09:00", "10:00", "Deep work")).json()["data"]
    far = (await log(client, p, "Far", DAY, "12:00", "13:00", "Deep work")).json()["data"]
    meet = (await log(client, p, "Meet", DAY, "10:00", "11:00", "Meetings")).json()["data"]
    r = await client.post(f"{API}/activities/merge", headers=p.headers, json={"activity_ids": [a["id"], far["id"]]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "MERGE_NOT_CONTIGUOUS"
    r = await client.post(f"{API}/activities/merge", headers=p.headers, json={"activity_ids": [a["id"], meet["id"]]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CATEGORY_REQUIRED"
    r = await client.post(f"{API}/activities/merge", headers=p.headers, json={"activity_ids": [a["id"], meet["id"]], "category_id": p.cats["Meetings"]})
    assert r.status_code == 200 and r.json()["data"]["category"]["name"] == "Meetings"


async def test_merge_absorbs_a_small_gap(client):
    p = await signup(client)
    a = (await log(client, p, "A", DAY, "09:00", "10:00")).json()["data"]
    b = (await log(client, p, "B", DAY, "10:05", "11:00")).json()["data"]
    r = await client.post(f"{API}/activities/merge", headers=p.headers, json={"activity_ids": [a["id"], b["id"]]})
    assert r.status_code == 200 and r.json()["data"]["duration_minutes"] == 120  # the 5 min gap is absorbed


async def test_ac035_delete_then_restore_keeps_tags_and_task(client, db):
    p = await signup(client)
    task = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "T"})).json()["data"]
    a = (await log(client, p, "Work", DAY, "09:00", "10:00", tag_ids=[p.tags["bug"]], task_id=task["id"])).json()["data"]
    assert (await client.delete(f"{API}/activities/{a['id']}", headers=p.headers)).status_code == 204
    assert (await client.get(f"{API}/activities/{a['id']}", headers=p.headers)).status_code == 404
    assert (await db.execute(text("SELECT count(*) FROM activity_day_slices"))).scalar_one() == 0
    await log(client, p, "Replacement", DAY, "09:00", "10:00")  # the slot is free while deleted
    blocked = await client.post(f"{API}/activities/{a['id']}/restore", headers=p.headers)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "ACTIVITY_OVERLAP"
    other = (await client.get(f"{API}/activities", headers=p.headers)).json()["data"][0]
    await client.delete(f"{API}/activities/{other['id']}", headers=p.headers)
    r = await client.post(f"{API}/activities/{a['id']}/restore", headers=p.headers)
    assert r.status_code == 200 and [t["name"] for t in r.json()["data"]["tags"]] == ["bug"] and r.json()["data"]["task_id"] == task["id"]
    assert await invariants_ok(db, p)


async def test_ac031_sleep_across_midnight_is_stored_once_and_sliced_per_day(client, db):
    p = await signup(client)
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "Sleep", "category_id": p.cats["Sleep"],
                          "start_at": at("2025-06-02", "23:00"), "end_at": at("2025-06-03", "07:00")})
    assert r.status_code == 201 and r.json()["data"]["duration_minutes"] == 480
    rows = (await db.execute(text("SELECT local_date::text, minutes FROM activity_day_slices ORDER BY local_date"))).all()
    assert rows == [("2025-06-02", 60), ("2025-06-03", 420)]
    assert (await db.execute(text("SELECT count(*) FROM activities"))).scalar_one() == 1
    assert await invariants_ok(db, p)


async def test_ac034_filter_by_tag_and_category_and_search(client):
    p = await signup(client)
    await log(client, p, "Fix login bug", DAY, "09:00", "10:00", "Deep work", tag_ids=[p.tags["p0"]], description="oauth redirect")
    await log(client, p, "Standup", DAY, "10:00", "10:30", "Meetings", tag_ids=[p.tags["p0"], p.tags["meetings"]])
    await log(client, p, "Admin", DAY, "11:00", "12:00", "Admin")
    work = (await client.get(f"{API}/categories", headers=p.headers)).json()["data"][0]
    assert work["name"] == "Work"
    q = f"{API}/activities?tag_ids={p.tags['p0']}&category_id={work['id']}"
    r = await client.get(q, headers=p.headers)
    assert sorted(a["title"] for a in r.json()["data"]) == ["Fix login bug", "Standup"]
    r = await client.get(f"{API}/activities?tag_ids={p.tags['p0']}&tag_ids={p.tags['meetings']}&tag_mode=all", headers=p.headers)
    assert [a["title"] for a in r.json()["data"]] == ["Standup"]
    r = await client.get(f"{API}/activities?category_id={p.cats['Meetings']}", headers=p.headers)
    assert [a["title"] for a in r.json()["data"]] == ["Standup"]
    r = await client.get(f"{API}/activities?q=oauth", headers=p.headers)
    assert [a["title"] for a in r.json()["data"]] == ["Fix login bug"]
    r = await client.get(f"{API}/activities?from=2025-06-03&to=2025-06-04", headers=p.headers)
    assert r.json()["data"] == []
    assert (await client.get(f"{API}/activities?from=2024-01-01&to=2025-12-31", headers=p.headers)).status_code == 422


async def test_pagination_is_stable_with_cursor(client):
    p = await signup(client)
    for h in range(8, 14):
        await log(client, p, f"Block {h}", DAY, f"{h:02d}:00", f"{h:02d}:30")
    seen, cursor = [], None
    for _ in range(4):
        r = await client.get(f"{API}/activities?limit=2" + (f"&cursor={cursor}" if cursor else ""), headers=p.headers)
        seen += [a["title"] for a in r.json()["data"]]
        cursor = r.json()["meta"].get("next_cursor")
        if not cursor:
            break
    assert seen == [f"Block {h}" for h in range(13, 7, -1)]


async def test_replace_tags_and_event_trail(client):
    p = await signup(client)
    a = (await log(client, p, "Work", DAY, "09:00", "10:00", tag_ids=[p.tags["bug"]])).json()["data"]
    r = await client.put(f"{API}/activities/{a['id']}/tags", headers=p.headers, json={"tag_ids": [p.tags["p0"], p.tags["research"]]})
    assert sorted(t["name"] for t in r.json()["data"]["tags"]) == ["p0", "research"]
    ev = [e["event_type"] for e in (await client.get(f"{API}/activities/{a['id']}/events", headers=p.headers)).json()["data"]]
    assert ev == ["created", "tagged", "untagged"]
    bad = await client.put(f"{API}/activities/{a['id']}/tags", headers=p.headers, json={"tag_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert bad.status_code == 422


async def test_archived_tags_and_categories_cannot_be_applied(client):
    p = await signup(client)
    await client.patch(f"{API}/tags/{p.tags['bug']}", headers=p.headers, json={"archived": True})
    r = await log(client, p, "x", DAY, "09:00", "10:00", tag_ids=[p.tags["bug"]])
    assert r.status_code == 422 and r.json()["error"]["code"] == "TAG_ARCHIVED"
    blocked = await client.patch(f"{API}/categories/{p.cats['Admin']}", headers=p.headers, json={"archived": True})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CATEGORY_ALLOCATED"  # Admin is in the Ideal Day
    assert (await client.patch(f"{API}/categories/{p.cats['Sales & clients']}", headers=p.headers, json={"archived": True})).status_code == 200
    r = await log(client, p, "x", DAY, "09:00", "10:00", "Sales & clients")
    assert r.status_code == 422 and r.json()["error"]["code"] == "CATEGORY_ARCHIVED"


async def test_duplicate_goes_after_the_original_and_respects_overlap(client):
    p = await signup(client)
    a = (await log(client, p, "Gym", DAY, "07:00", "08:00", "Health", tag_ids=[p.tags["p1"]])).json()["data"]
    d = await client.post(f"{API}/activities/{a['id']}/duplicate", headers=p.headers, json={})
    assert d.status_code == 201 and d.json()["data"]["start_at"] == a["end_at"] and d.json()["data"]["origin"] == "duplicate"
    assert [t["name"] for t in d.json()["data"]["tags"]] == ["p1"]
    again = await client.post(f"{API}/activities/{a['id']}/duplicate", headers=p.headers)
    assert again.status_code == 409  # that slot is now taken
    elsewhere = await client.post(f"{API}/activities/{a['id']}/duplicate", headers=p.headers, json={"start_at": at(DAY, "18:00")})
    assert elsewhere.status_code == 201


async def test_bulk_operations_are_atomic_and_limited(client, db):
    p = await signup(client)
    ids = [(await log(client, p, f"B{h}", DAY, f"{h:02d}:00", f"{h:02d}:30")).json()["data"]["id"] for h in (8, 9, 10)]
    r = await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": ids, "op": "add_tags", "value": [p.tags["p0"], p.tags["bug"]]})
    assert r.json()["data"]["updated"] == 3
    r = await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": ids, "op": "remove_tags", "value": [p.tags["bug"]]})
    r = await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": ids, "op": "set_category", "value": p.cats["Learning"]})
    assert r.json()["data"]["updated"] == 3
    cats = (await db.execute(text("SELECT DISTINCT category_id::text FROM activity_day_slices"))).scalars().all()
    assert cats == [p.cats["Learning"]]
    listed = (await client.get(f"{API}/activities", headers=p.headers)).json()["data"]
    assert all([t["name"] for t in a["tags"]] == ["p0"] for a in listed)
    missing = await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": [*ids, "00000000-0000-0000-0000-000000000000"], "op": "delete"})
    assert missing.status_code == 404
    assert len((await client.get(f"{API}/activities", headers=p.headers)).json()["data"]) == 3  # nothing was deleted
    assert (await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": ids, "op": "delete"})).json()["data"]["updated"] == 3
    assert (await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": [ids[0]] * 101, "op": "delete"})).status_code in (404, 422)
    too_many = [f"00000000-0000-0000-0000-{i:012d}" for i in range(101)]
    assert (await client.post(f"{API}/activities/bulk", headers=p.headers, json={"ids": too_many, "op": "delete"})).status_code == 422


async def test_activity_detail_lists_other_activities_with_the_same_tag(client):
    p = await signup(client)
    a = (await log(client, p, "A", DAY, "09:00", "10:00", tag_ids=[p.tags["p0"]])).json()["data"]
    await log(client, p, "B", DAY, "10:00", "11:00", tag_ids=[p.tags["p0"]])
    await log(client, p, "C", DAY, "11:00", "12:00")
    d = (await client.get(f"{API}/activities/{a['id']}", headers=p.headers)).json()["data"]
    assert [x["title"] for x in d["also_tagged"]] == ["B"] and d["source"]["quote"] is None


__all__ = ["utc", "Activity", "ActivityStatus", "Placement"]
