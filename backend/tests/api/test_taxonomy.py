import pytest

from tests.factories import log, signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"
DAY = "2025-06-02"


async def test_onboarding_seeds_taxonomy_and_an_ideal_day_that_is_exactly_24h(client, db):
    from sqlalchemy import text

    p = await signup(client)
    assert {"Work", "Personal", "Sleep", "Deep work", "Meetings", "Transitions", "Family & friends"} <= set(p.cats)
    assert {"research", "meetings", "bug", "p0", "p1", "social-media"} <= set(p.tags)
    total = (await db.execute(text("SELECT sum(minutes) FROM ideal_allocations"))).scalar_one()
    assert total == 1440
    tree = (await client.get(f"{API}/categories", headers=p.headers)).json()["data"]
    work = next(n for n in tree if n["name"] == "Work")
    assert work["color"] and [c["name"] for c in work["children"]][:2] == ["Deep work", "Meetings"]
    assert next(c for c in work["children"] if c["name"] == "Deep work")["counts_as_focus"] is True
    again = await client.post(f"{API}/users/me/onboarding", headers=p.headers, json={"timezone": "Asia/Kolkata", "seed": "default", "ideal_day_preset": "balanced"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_ONBOARDED"


async def test_empty_onboarding_keeps_only_the_roots(client):
    p = await signup(client, seed="empty")
    assert sorted(p.cats) == ["Personal", "Sleep", "Work"] and p.tags == {}


async def test_category_create_depth_and_name_rules(client):
    p = await signup(client)
    r = await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Deep work"], "name": "Clients"})
    assert r.status_code == 201 and r.json()["data"]["depth"] == 3 and r.json()["data"]["path_names"] == "Work › Deep work › Clients"
    deeper = await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": r.json()["data"]["id"], "name": "Acme"})
    assert deeper.status_code == 422 and deeper.json()["error"]["code"] == "CATEGORY_DEPTH_EXCEEDED"
    dup = await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Deep work"], "name": "clients"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "NAME_TAKEN"
    same_name_elsewhere = await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Meetings"], "name": "Clients"})
    assert same_name_elsewhere.status_code == 201


async def test_system_roots_are_protected(client):
    p = await signup(client)
    for call in (
        client.patch(f"{API}/categories/{p.cats['Work']}", headers=p.headers, json={"name": "Job"}),
        client.patch(f"{API}/categories/{p.cats['Work']}", headers=p.headers, json={"archived": True}),
        client.delete(f"{API}/categories/{p.cats['Sleep']}", headers=p.headers),
    ):
        r = await call
        assert r.status_code == 409 and r.json()["error"]["code"] == "CATEGORY_SYSTEM"
    ok = await client.patch(f"{API}/categories/{p.cats['Work']}", headers=p.headers, json={"color": "#112233"})
    assert ok.status_code == 200 and ok.json()["data"]["color"] == "#112233"


async def test_ac043_rename_keeps_ids_and_paths_follow(client):
    p = await signup(client)
    child = (await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Deep work"], "name": "Clients"})).json()["data"]
    a = (await log(client, p, "Work", DAY, "09:00", "10:00", "Deep work")).json()["data"]
    r = await client.patch(f"{API}/categories/{p.cats['Deep work']}", headers=p.headers, json={"name": "Focus work"})
    assert r.status_code == 200 and r.json()["data"]["path_names"] == "Work › Focus work"
    assert (await client.get(f"{API}/activities/{a['id']}", headers=p.headers)).json()["data"]["category"]["name"] == "Focus work"
    tree = (await client.get(f"{API}/categories", headers=p.headers)).json()["data"]
    work = next(n for n in tree if n["name"] == "Work")
    clients = next(c for c in next(x for x in work["children"] if x["id"] == p.cats["Deep work"])["children"] if c["id"] == child["id"])
    assert clients["path_names"] == "Work › Focus work › Clients"


async def test_ac044_category_with_activities_cannot_be_deleted(client):
    p = await signup(client)
    await log(client, p, "x", DAY, "09:00", "10:00", "Sales & clients")
    r = await client.delete(f"{API}/categories/{p.cats['Sales & clients']}", headers=p.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CATEGORY_IN_USE"
    unused = await client.delete(f"{API}/categories/{p.cats['Learning']}", headers=p.headers)
    assert unused.status_code == 409 and unused.json()["error"]["code"] == "CATEGORY_ALLOCATED"  # in the Ideal Day
    fresh = (await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Work"], "name": "Scratch"})).json()["data"]
    assert (await client.delete(f"{API}/categories/{fresh['id']}", headers=p.headers)).status_code == 204


async def test_ac045_cross_root_move_refused_when_activities_exist(client):
    p = await signup(client)
    await log(client, p, "x", DAY, "09:00", "10:00", "Sales & clients")
    r = await client.patch(f"{API}/categories/{p.cats['Sales & clients']}", headers=p.headers, json={"parent_id": p.cats["Personal"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CROSS_ROOT_MOVE"
    empty = (await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Work"], "name": "Side project"})).json()["data"]
    moved = await client.patch(f"{API}/categories/{empty['id']}", headers=p.headers, json={"parent_id": p.cats["Personal"]})
    assert moved.status_code == 200 and moved.json()["data"]["root_kind"] == "personal" and moved.json()["data"]["path_names"] == "Personal › Side project"


async def test_category_move_within_root_repaths_descendants_and_blocks_cycles(client):
    p = await signup(client)
    a = (await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": p.cats["Work"], "name": "A"})).json()["data"]
    b = (await client.post(f"{API}/categories", headers=p.headers, json={"parent_id": a["id"], "name": "B"})).json()["data"]
    cycle = await client.patch(f"{API}/categories/{a['id']}", headers=p.headers, json={"parent_id": b["id"]})
    assert cycle.status_code == 422 and cycle.json()["error"]["code"] == "CATEGORY_CYCLE"
    too_deep = await client.patch(f"{API}/categories/{a['id']}", headers=p.headers, json={"parent_id": p.cats["Deep work"]})
    assert too_deep.status_code == 422 and too_deep.json()["error"]["code"] == "CATEGORY_DEPTH_EXCEEDED"  # A(1)+B(1) under depth-2 parent = 4
    moved = await client.patch(f"{API}/categories/{b['id']}", headers=p.headers, json={"parent_id": p.cats["Meetings"]})
    assert moved.json()["data"]["path_names"] == "Work › Meetings › B" and moved.json()["data"]["depth"] == 3


async def test_category_merge_repoints_activities_and_archives_source(client, db):
    from sqlalchemy import text

    p = await signup(client)
    await log(client, p, "x", DAY, "09:00", "10:00", "Sales & clients")
    await log(client, p, "y", DAY, "11:00", "12:00", "Sales & clients")
    prev = await client.post(f"{API}/categories/{p.cats['Sales & clients']}/merge", headers=p.headers, json={"target_id": p.cats["Admin"], "preview": True})
    assert prev.json()["data"] == {"moved_activities": 2, "moved_allocations": 0, "preview": True}
    r = await client.post(f"{API}/categories/{p.cats['Sales & clients']}/merge", headers=p.headers, json={"target_id": p.cats["Admin"]})
    assert r.status_code == 200 and r.json()["data"]["moved_activities"] == 2
    cats = (await db.execute(text("SELECT DISTINCT category_id::text FROM activity_day_slices"))).scalars().all()
    assert cats == [p.cats["Admin"]]
    tree = (await client.get(f"{API}/categories", headers=p.headers)).json()["data"]
    assert "Sales & clients" not in [c["name"] for n in tree for c in n["children"]]
    cross = await client.post(f"{API}/categories/{p.cats['Learning']}/merge", headers=p.headers, json={"target_id": p.cats["Health"]})
    assert cross.status_code == 422 and cross.json()["error"]["code"] == "CROSS_ROOT_MERGE"
    self_merge = await client.post(f"{API}/categories/{p.cats['Admin']}/merge", headers=p.headers, json={"target_id": p.cats["Admin"]})
    assert self_merge.status_code == 422


async def test_category_merge_sums_ideal_allocations(client, db):
    from sqlalchemy import text

    p = await signup(client)
    before = (await db.execute(text("SELECT sum(minutes) FROM ideal_allocations"))).scalar_one()
    r = await client.post(f"{API}/categories/{p.cats['Admin']}/merge", headers=p.headers, json={"target_id": p.cats["Meetings"]})
    assert r.status_code == 200 and r.json()["data"]["moved_allocations"] == 1
    assert (await db.execute(text("SELECT sum(minutes) FROM ideal_allocations"))).scalar_one() == before == 1440
    assert (await db.execute(text("SELECT minutes FROM ideal_allocations WHERE category_id = :c"), {"c": p.cats["Meetings"]})).scalar_one() == 120


# ------------------------------------------------------------------------------------------------ tags


async def test_tag_names_are_normalised_and_unique(client):
    p = await signup(client)
    r = await client.post(f"{API}/tags", headers=p.headers, json={"name": "#Product-B"})
    assert r.status_code == 201 and r.json()["data"]["name"] == "product-b" and r.json()["data"]["color"].startswith("#")
    assert (await client.post(f"{API}/tags", headers=p.headers, json={"name": "product-b"})).json()["error"]["code"] == "NAME_TAKEN"
    assert (await client.post(f"{API}/tags", headers=p.headers, json={"name": "has space"})).status_code == 422
    assert (await client.post(f"{API}/tags", headers=p.headers, json={"name": "client:acme"})).status_code == 201


async def test_ac046_goal_status_over_when_weekly_cap_is_exceeded(client):
    p = await signup(client)
    # social-media is max 300 min; log 370 min across the week of 2025-06-02
    await log(client, p, "Scrolling", "2025-06-02", "20:00", "22:00", "Entertainment", tag_ids=[p.tags["social-media"]])  # 120
    await log(client, p, "Scrolling", "2025-06-03", "20:00", "23:10", "Entertainment", tag_ids=[p.tags["social-media"]])  # 190
    await log(client, p, "Scrolling", "2025-06-04", "20:00", "21:00", "Entertainment", tag_ids=[p.tags["social-media"]])  # 60
    r = await client.get(f"{API}/tags?from=2025-06-02&to=2025-06-08", headers=p.headers)
    tag = next(t for t in r.json()["data"] if t["name"] == "social-media")
    assert tag["minutes_in_range"] == 370 and tag["goal_status"] == "over"
    r = await client.get(f"{API}/tags?from=2025-06-02&to=2025-06-03", headers=p.headers)
    tag = next(t for t in r.json()["data"] if t["name"] == "social-media")
    assert tag["minutes_in_range"] == 310 and tag["goal_status"] == "over"
    r = await client.get(f"{API}/tags?from=2025-06-09&to=2025-06-15", headers=p.headers)
    assert next(t for t in r.json()["data"] if t["name"] == "social-media")["goal_status"] == "ok"


async def test_goal_validation(client):
    p = await signup(client)
    assert (await client.post(f"{API}/tags", headers=p.headers, json={"name": "cap", "goal_kind": "max"})).status_code == 422
    ok = await client.post(f"{API}/tags", headers=p.headers, json={"name": "cap", "goal_kind": "min", "goal_weekly_minutes": 600})
    assert ok.status_code == 201
    back = await client.patch(f"{API}/tags/{ok.json()['data']['id']}", headers=p.headers, json={"goal_kind": "tracked", "goal_weekly_minutes": None})
    assert back.status_code == 200 and back.json()["data"]["goal_weekly_minutes"] is None and back.json()["data"]["goal_status"] == "none"


async def test_ac048_category_totals_count_once_while_tags_overlap(client):
    p = await signup(client)
    await log(client, p, "Focus", DAY, "09:00", "11:00", "Deep work", tag_ids=[p.tags["p0"], p.tags["bug"], p.tags["research"]])
    tags = {t["name"]: t["minutes_in_range"] for t in (await client.get(f"{API}/tags?from={DAY}&to={DAY}", headers=p.headers)).json()["data"]}
    assert tags["p0"] == tags["bug"] == tags["research"] == 120  # overlay: each tag gets the full duration


async def test_ac041_ac042_tag_merge_keeps_history_and_dedupes(client):
    p = await signup(client)
    a = (await client.post(f"{API}/tags", headers=p.headers, json={"name": "prod-b"})).json()["data"]
    b = (await client.post(f"{API}/tags", headers=p.headers, json={"name": "product-b"})).json()["data"]
    await log(client, p, "One", DAY, "09:00", "12:00", tag_ids=[a["id"]])  # A: 3h
    await log(client, p, "Two", DAY, "13:00", "15:00", tag_ids=[b["id"]])  # B: 2h
    both = (await log(client, p, "Both", DAY, "16:00", "17:00", tag_ids=[a["id"], b["id"]])).json()["data"]
    prev = await client.post(f"{API}/tags/{a['id']}/merge", headers=p.headers, json={"target_id": b["id"], "preview": True})
    assert prev.json()["data"] == {"moved_links": 1, "deduplicated": 1, "preview": True}
    r = await client.post(f"{API}/tags/{a['id']}/merge", headers=p.headers, json={"target_id": b["id"]})
    assert r.status_code == 200 and r.json()["data"] == {"moved_links": 1, "deduplicated": 1, "preview": False}
    tags = {t["name"]: t for t in (await client.get(f"{API}/tags?from={DAY}&to={DAY}", headers=p.headers)).json()["data"]}
    assert "prod-b" not in tags and tags["product-b"]["minutes_in_range"] == 360 and "prod-b" in tags["product-b"]["aliases"]
    d = (await client.get(f"{API}/activities/{both['id']}", headers=p.headers)).json()["data"]
    assert [t["name"] for t in d["tags"]] == ["product-b"]  # appears once
    archived = (await client.get(f"{API}/tags?archived=true", headers=p.headers)).json()["data"]
    assert any(t["name"] == "prod-b" and t["archived"] for t in archived)
    bad = await client.post(f"{API}/tags/{b['id']}/merge", headers=p.headers, json={"target_id": b["id"]})
    assert bad.status_code == 422


async def test_rename_with_alias_delete_unused_and_in_use(client):
    p = await signup(client)
    t = (await client.post(f"{API}/tags", headers=p.headers, json={"name": "old-name"})).json()["data"]
    r = await client.patch(f"{API}/tags/{t['id']}", headers=p.headers, json={"name": "new-name", "keep_old_name_as_alias": True})
    assert r.json()["data"]["name"] == "new-name" and r.json()["data"]["aliases"] == ["old-name"]
    clash = await client.post(f"{API}/tags", headers=p.headers, json={"name": "old-name"})
    assert clash.status_code == 409  # the alias reserves the name
    await log(client, p, "x", DAY, "09:00", "10:00", tag_ids=[t["id"]])
    used = await client.delete(f"{API}/tags/{t['id']}", headers=p.headers)
    assert used.status_code == 409 and used.json()["error"]["code"] == "TAG_IN_USE"
    spare = (await client.post(f"{API}/tags", headers=p.headers, json={"name": "spare"})).json()["data"]
    assert (await client.delete(f"{API}/tags/{spare['id']}", headers=p.headers)).status_code == 204


async def test_aliases_rules_and_tag_detail(client):
    p = await signup(client)
    r = await client.put(f"{API}/tags/{p.tags['bug']}/aliases", headers=p.headers, json={"aliases": ["defect", "Defect", "issue"]})
    assert r.json()["data"] == ["defect", "issue"]
    taken = await client.put(f"{API}/tags/{p.tags['p0']}/aliases", headers=p.headers, json={"aliases": ["issue"]})
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "ALIAS_TAKEN"
    is_name = await client.put(f"{API}/tags/{p.tags['p0']}/aliases", headers=p.headers, json={"aliases": ["research"]})
    assert is_name.status_code == 409
    rule = await client.post(f"{API}/keyword-rules", headers=p.headers, json={"phrase": "  Hotfix ", "target_type": "tag", "target_id": p.tags["bug"]})
    assert rule.status_code == 201 and rule.json()["data"]["phrase"] == "hotfix" and rule.json()["data"]["target_name"] == "bug"
    dup = await client.post(f"{API}/keyword-rules", headers=p.headers, json={"phrase": "hotfix", "target_type": "tag", "target_id": p.tags["bug"]})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "RULE_EXISTS"
    rules = (await client.get(f"{API}/keyword-rules?target_type=tag&target_id={p.tags['bug']}", headers=p.headers)).json()["data"]
    assert sorted(x["phrase"] for x in rules) == ["debugging", "hotfix"]
    await log(client, p, "Fix", DAY, "09:00", "10:00", tag_ids=[p.tags["bug"]])
    detail = (await client.get(f"{API}/tags/{p.tags['bug']}?from={DAY}&to=2025-06-04", headers=p.headers)).json()["data"]
    assert [d["minutes"] for d in detail["by_day"]] == [60, 0, 0] and detail["total_minutes"] == 60
    assert detail["keywords"] == ["debugging", "hotfix"] and detail["recent_activities"][0]["title"] == "Fix"
    assert (await client.delete(f"{API}/keyword-rules/{rule.json()['data']['id']}", headers=p.headers)).status_code == 204
