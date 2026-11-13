import pytest

from tests.factories import log, signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def test_task_crud_filters_and_status(client):
    p = await signup(client)
    proj = (await client.post(f"{API}/projects", headers=p.headers, json={"name": "Product B", "color": "#3E86D4"})).json()["data"]
    assert (await client.post(f"{API}/projects", headers=p.headers, json={"name": "product b"})).json()["error"]["code"] == "NAME_TAKEN"
    t1 = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Fix sync", "project_id": proj["id"], "priority": 0, "due_date": "2025-06-20"})).json()["data"]
    t2 = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Write docs"})).json()["data"]
    assert t1["status"] == "open" and t1["logged_minutes"] == 0 and t1["overdue"] is True and t1["days_left"] < 0
    listed = (await client.get(f"{API}/tasks", headers=p.headers)).json()["data"]
    assert [t["title"] for t in listed] == ["Write docs", "Fix sync"]
    assert [t["title"] for t in (await client.get(f"{API}/tasks?project_id={proj['id']}", headers=p.headers)).json()["data"]] == ["Fix sync"]
    assert [t["title"] for t in (await client.get(f"{API}/tasks?priority=0", headers=p.headers)).json()["data"]] == ["Fix sync"]
    assert [t["title"] for t in (await client.get(f"{API}/tasks?q=docs", headers=p.headers)).json()["data"]] == ["Write docs"]
    done = await client.patch(f"{API}/tasks/{t2['id']}", headers=p.headers, json={"status": "done"})
    assert done.json()["data"]["status"] == "done" and done.json()["data"]["completed_at"]
    assert [t["title"] for t in (await client.get(f"{API}/tasks?status=open", headers=p.headers)).json()["data"]] == ["Fix sync"]
    reopened = await client.patch(f"{API}/tasks/{t2['id']}", headers=p.headers, json={"status": "open"})
    assert reopened.json()["data"]["completed_at"] is None
    cleared = await client.patch(f"{API}/tasks/{t1['id']}", headers=p.headers, json={"clear": ["due_date", "project_id"]})
    assert cleared.json()["data"]["due_date"] is None and cleared.json()["data"]["project_id"] is None
    assert (await client.patch(f"{API}/tasks/{t1['id']}", headers=p.headers, json={"clear": ["title"]})).status_code == 422
    stale = await client.patch(f"{API}/tasks/{t1['id']}", headers=p.headers, json={"version": 1, "title": "x"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_ac037_by_day_sums_to_total_and_ac038_deleting_a_task_keeps_activities(client):
    p = await signup(client)
    task = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Sync fix"})).json()["data"]
    ids = []
    for day, s, e in (("2025-06-02", "09:00", "11:00"), ("2025-06-03", "09:00", "10:30"), ("2025-06-05", "14:00", "15:00")):
        ids.append((await log(client, p, "Work", day, s, e, task_id=task["id"])).json()["data"]["id"])
    d = (await client.get(f"{API}/tasks/{task['id']}", headers=p.headers)).json()["data"]
    assert d["rollup"]["total_minutes"] == 270 == sum(x["minutes"] for x in d["rollup"]["by_day"])
    assert [x["key"] for x in d["rollup"]["by_day"]] == ["2025-06-02", "2025-06-03", "2025-06-05"]
    assert d["rollup"]["by_week"] == [{"key": "2025-06-02", "minutes": 270}] and d["rollup"]["first_logged"] == "2025-06-02"
    assert d["logged_minutes"] == 270 and len(d["activities"]) == 3
    assert (await client.get(f"{API}/tasks?has_time=true", headers=p.headers)).json()["data"][0]["id"] == task["id"]
    assert (await client.delete(f"{API}/tasks/{task['id']}", headers=p.headers)).status_code == 204
    assert (await client.get(f"{API}/tasks/{task['id']}", headers=p.headers)).status_code == 404
    for i in ids:
        a = (await client.get(f"{API}/activities/{i}", headers=p.headers)).json()["data"]
        assert a["task_id"] is None


async def test_ac040_marking_a_task_done_does_not_change_logged_time(client):
    p = await signup(client)
    task = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "T"})).json()["data"]
    await log(client, p, "Work", "2025-06-02", "09:00", "10:00", task_id=task["id"])
    await client.patch(f"{API}/tasks/{task['id']}", headers=p.headers, json={"status": "dropped"})
    d = (await client.get(f"{API}/tasks/{task['id']}", headers=p.headers)).json()["data"]
    assert d["logged_minutes"] == 60 and d["status"] == "dropped"


async def test_project_rollups_archive_and_rename(client):
    p = await signup(client)
    proj = (await client.post(f"{API}/projects", headers=p.headers, json={"name": "Alpha"})).json()["data"]
    t = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "T", "project_id": proj["id"]})).json()["data"]
    await log(client, p, "Work", "2025-06-02", "09:00", "10:00", task_id=t["id"])
    listed = (await client.get(f"{API}/projects", headers=p.headers)).json()["data"]
    assert listed[0]["task_count"] == 1 and listed[0]["logged_minutes"] == 60
    r = await client.patch(f"{API}/projects/{proj['id']}", headers=p.headers, json={"name": "Alpha 2", "archived": True})
    assert r.json()["data"]["archived"] is True
    assert (await client.get(f"{API}/projects", headers=p.headers)).json()["data"] == []
    assert len((await client.get(f"{API}/projects?archived=true", headers=p.headers)).json()["data"]) == 1
    assert (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "x", "project_id": "00000000-0000-0000-0000-000000000000"})).status_code == 422


async def test_deadlines_helper_counts_days_left(client):
    from datetime import UTC, datetime, timedelta

    p = await signup(client, tz="Asia/Kolkata")
    soon = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    t = (await client.post(f"{API}/tasks", headers=p.headers, json={"title": "Ship", "due_date": soon})).json()["data"]
    assert t["overdue"] is False and t["days_left"] in (2, 3, 4)
