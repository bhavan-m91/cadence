"""AC-002 / FR-011: another user's resource is always a plain 404, never 403, on every router."""

import pytest

from tests.factories import log, signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"
DAY = "2025-06-02"
MISSING = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
async def two(client):
    a = await signup(client)
    b = await signup(client)
    act = (await log(client, a, "Secret", DAY, "09:00", "10:00", tag_ids=[a.tags["p0"]])).json()["data"]
    task = (await client.post(f"{API}/tasks", headers=a.headers, json={"title": "Private task"})).json()["data"]
    proj = (await client.post(f"{API}/projects", headers=a.headers, json={"name": "Private proj"})).json()["data"]
    rule = (await client.post(f"{API}/keyword-rules", headers=a.headers, json={"phrase": "zzz", "target_type": "tag", "target_id": a.tags["bug"]})).json()["data"]
    return a, b, {"act": act["id"], "task": task["id"], "proj": proj["id"], "rule": rule["id"]}


async def test_activity_endpoints_return_404_for_other_users(client, two):
    a, b, ids = two
    h = b.headers
    calls = [
        client.get(f"{API}/activities/{ids['act']}", headers=h),
        client.patch(f"{API}/activities/{ids['act']}", headers=h, json={"version": 1, "title": "hacked"}),
        client.delete(f"{API}/activities/{ids['act']}", headers=h),
        client.post(f"{API}/activities/{ids['act']}/restore", headers=h),
        client.post(f"{API}/activities/{ids['act']}/split", headers=h, json={"at": "2025-06-02T09:30:00+05:30"}),
        client.post(f"{API}/activities/{ids['act']}/duplicate", headers=h, json={}),
        client.put(f"{API}/activities/{ids['act']}/tags", headers=h, json={"tag_ids": []}),
        client.get(f"{API}/activities/{ids['act']}/events", headers=h),
        client.post(f"{API}/activities/{ids['act']}/mark-done", headers=h, json={}),
        client.post(f"{API}/activities/merge", headers=h, json={"activity_ids": [ids["act"], MISSING]}),
        client.post(f"{API}/activities/bulk", headers=h, json={"ids": [ids["act"]], "op": "delete"}),
    ]
    for call in calls:
        r = await call
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "NOT_FOUND"
    assert (await client.get(f"{API}/activities/{ids['act']}", headers=a.headers)).json()["data"]["title"] == "Secret"


async def test_foreign_ids_in_a_body_look_like_unknown_ids(client, two):
    a, b, ids = two
    cat = await client.post(f"{API}/activities", headers=b.headers, json={"title": "x", "category_id": a.cats["Deep work"], "start_at": "2025-06-02T09:00:00+05:30", "end_at": "2025-06-02T10:00:00+05:30"})
    assert cat.status_code == 422 and "Unknown category" in cat.json()["error"]["message"]
    tag = await client.post(f"{API}/activities", headers=b.headers, json={"title": "x", "category_id": b.cats["Deep work"], "tag_ids": [a.tags["p0"]], "start_at": "2025-06-02T09:00:00+05:30", "end_at": "2025-06-02T10:00:00+05:30"})
    assert tag.status_code == 422
    task = await client.post(f"{API}/activities", headers=b.headers, json={"title": "x", "category_id": b.cats["Deep work"], "task_id": ids["task"], "start_at": "2025-06-02T09:00:00+05:30", "end_at": "2025-06-02T10:00:00+05:30"})
    assert task.status_code == 422
    assert (await client.post(f"{API}/tasks", headers=b.headers, json={"title": "x", "project_id": ids["proj"]})).status_code == 422


async def test_task_project_taxonomy_and_rule_endpoints_return_404(client, two):
    a, b, ids = two
    h = b.headers
    calls = [
        client.get(f"{API}/tasks/{ids['task']}", headers=h), client.patch(f"{API}/tasks/{ids['task']}", headers=h, json={"title": "x"}),
        client.delete(f"{API}/tasks/{ids['task']}", headers=h), client.patch(f"{API}/projects/{ids['proj']}", headers=h, json={"name": "x"}),
        client.patch(f"{API}/categories/{a.cats['Admin']}", headers=h, json={"color": "#000000"}),
        client.delete(f"{API}/categories/{a.cats['Admin']}", headers=h),
        client.post(f"{API}/categories/{a.cats['Admin']}/merge", headers=h, json={"target_id": b.cats["Meetings"]}),
        client.post(f"{API}/categories/{b.cats['Admin']}/merge", headers=h, json={"target_id": a.cats["Meetings"]}),
        client.get(f"{API}/tags/{a.tags['p0']}", headers=h), client.patch(f"{API}/tags/{a.tags['p0']}", headers=h, json={"color": "#000000"}),
        client.delete(f"{API}/tags/{a.tags['p0']}", headers=h), client.put(f"{API}/tags/{a.tags['p0']}/aliases", headers=h, json={"aliases": ["x"]}),
        client.post(f"{API}/tags/{a.tags['p0']}/merge", headers=h, json={"target_id": b.tags["p1"]}),
        client.delete(f"{API}/keyword-rules/{ids['rule']}", headers=h),
        client.get(f"{API}/exports/{MISSING}", headers=h),
    ]
    for call in calls:
        r = await call
        assert r.status_code == 404, (r.request.method, r.request.url, r.text)


async def test_lists_never_leak_other_users_data(client, two):
    a, b, ids = two
    h = b.headers
    assert (await client.get(f"{API}/activities", headers=h)).json()["data"] == []
    assert (await client.get(f"{API}/tasks", headers=h)).json()["data"] == []
    assert (await client.get(f"{API}/projects", headers=h)).json()["data"] == []
    tl = (await client.get(f"{API}/timeline?from={DAY}&to={DAY}", headers=h)).json()["data"]["days"][0]
    assert tl["blocks"] == [] and tl["coverage"]["logged"] == 0
    tags = {t["id"] for t in (await client.get(f"{API}/tags", headers=h)).json()["data"]}
    assert tags.isdisjoint(a.tags.values())
    cats = {c for c in b.cats.values()}
    assert cats.isdisjoint(a.cats.values())
    tag = next(t for t in (await client.get(f"{API}/tags?from={DAY}&to={DAY}", headers=h)).json()["data"] if t["name"] == "p0")
    assert tag["minutes_in_range"] == 0
    rules = (await client.get(f"{API}/keyword-rules", headers=h)).json()["data"]
    assert ids["rule"] not in {r["id"] for r in rules}


async def test_export_is_scoped_and_complete(client, db, two):
    a, b, ids = two
    import io
    import json
    import uuid
    import zipfile

    from app.services import email_service
    from app.services.export_service import run_export

    token = email_service.OUTBOX[0].link.split("token=")[1]  # user A's verification mail
    assert (await client.post(f"{API}/auth/verify-email", json={"token": token})).status_code == 200
    r = await client.post(f"{API}/users/me/exports", headers=a.headers)
    assert r.status_code == 202
    job_id = r.json()["data"]["id"]
    await run_export(db, uuid.UUID(job_id))
    status = (await client.get(f"{API}/exports/{job_id}", headers=a.headers)).json()["data"]
    assert status["status"] == "succeeded" and status["download_url"].endswith("/download") and status["expires_at"]
    assert (await client.get(f"{API}/exports/{job_id}", headers=b.headers)).status_code == 404
    assert (await client.get(f"{API}/exports/{job_id}/download", headers=b.headers)).status_code == 404
    dl = await client.get(status["download_url"], headers=a.headers)
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(dl.content))
    assert {"profile.json", "activities.json", "tasks.json", "tags.json", "categories.json"} <= set(z.namelist())
    activities = json.loads(z.read("activities.json"))
    assert [x["title"] for x in activities] == ["Secret"]
    profile = json.loads(z.read("profile.json"))
    assert profile["user"]["password_hash"] is None and profile["user"]["email"] == a.email
    assert all(x["user_id"] == a.id for x in activities)
