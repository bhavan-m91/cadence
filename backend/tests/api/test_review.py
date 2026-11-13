import uuid

import pytest
from sqlalchemy import text

from app.ai.providers.fake_provider import FixtureProvider
from tests.ai_fixtures import TEXT, prd_response
from tests.api.test_ideal import day_body
from tests.factories import create_entry, idem, log, signup, submit

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def review(client, p, entry_id, job_id=None):
    r = await client.get(f"{API}/journal-entries/{entry_id}/review" + (f"?job_id={job_id}" if job_id else ""), headers=p.headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def answer(client, p, entry_id, job_id, qid, value):
    return await client.post(f"{API}/journal-entries/{entry_id}/review/answers", headers=p.headers, json={"job_id": job_id, "question_id": qid, "value": value})


async def commit(client, p, entry_id, job_id, key=None, **body):
    return await client.post(f"{API}/journal-entries/{entry_id}/review/commit", headers={**p.headers, **idem(key)}, json={"job_id": job_id, **body})


async def commit_all(client, db, p, entry_id, *, answer_meeting="14:00", **body):
    """Process the PRD example, answer its one question and commit everything proposed."""
    job_id = await submit(client, db, p, entry_id, FixtureProvider(prd_response(p)))
    if answer_meeting:
        assert (await answer(client, p, entry_id, job_id, "start_time:a4", answer_meeting)).status_code == 200
    r = await commit(client, p, entry_id, job_id, **body)
    assert r.status_code == 200, r.text
    return job_id, r.json()["data"]


def by_title(drafts):
    return {d["title"]: d for d in drafts}


async def test_the_review_payload_for_the_prd_example(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    r = await review(client, p, e["id"])
    assert r["job"]["id"] == job_id and r["job"]["status"] == "succeeded" and r["job"]["provider"] == "fixture" and r["entry"]["status"] == "review"
    assert [d["temp_id"] for d in r["drafts"]] == ["a1", "a2", "a3", "a4", "a5"]
    d = {x["temp_id"]: x for x in r["drafts"]}
    assert (d["a1"]["start_at"][11:16], d["a1"]["end_at"][11:16], d["a1"]["duration_minutes"]) == ("04:00", "05:00", 60)   # 09:30-10:30 IST
    assert d["a2"]["time_certainty"] == "inferred" and d["a2"]["duration_minutes"] == 150
    assert d["a4"]["placement"] == "unplaced" and d["a4"]["start_at"] is None and d["a4"]["duration_minutes"] == 45
    assert d["a5"]["placement"] == "unplaced" and d["a5"]["duration_minutes"] is None
    assert {t["name"] for t in d["a2"]["tags"]} == {"bug", "product-a"} and next(t for t in d["a2"]["tags"] if t["name"] == "product-a")["new"] is True
    assert d["a3"]["source"]["quote"] == "Had lunch from 1 to 2" and TEXT[d["a3"]["source"]["start"]:d["a3"]["source"]["end"]] == "Had lunch from 1 to 2"
    assert [d[k]["band"] for k in ("a1", "a2", "a3", "a4", "a5")] == ["medium", "high", "high", "low", "low"]
    s = r["summary"]
    assert (s["activity_count"], s["gap_count"], s["not_mentioned_minutes"], s["to_double_check"]) == (5, 2, 270, 3)          # AC-025 style: gaps are listed with their total
    assert [(g["start_at"][11:16], g["minutes"]) for g in r["gaps"]] == [("03:30", 30), ("08:30", 240)]
    assert len(r["questions"]) == 1 and r["questions"][0]["id"] == "start_time:a4" and r["questions"][0]["options"][0]["value"] == "14:00"
    assert sorted((b["reason"], b["draft_id"]) for b in r["blocking"]) == sorted([("UNANSWERED_QUESTION", d["a4"]["id"]), ("MISSING_DURATION", d["a5"]["id"])])
    assert r["conflicts"] == [] and r["ideal"] is None and r["replace_candidates"] == []


async def test_drafts_are_invisible_to_everything_until_commit(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    assert (await client.get(f"{API}/activities?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"] == []
    day = (await client.get(f"{API}/timeline?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]["days"][0]
    assert day["blocks"] == [] and day["coverage"]["logged"] == 0
    assert (await db.execute(text("SELECT count(*) FROM activity_day_slices"))).scalar_one() == 0
    assert (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'draft'"))).scalar_one() == 5


async def test_not_ready_before_the_worker_finishes(client):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    r = await client.get(f"{API}/journal-entries/{e['id']}/review", headers=p.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "JOB_NOT_READY"


async def test_answering_the_meeting_start_places_it_and_unblocks_product_b(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    r = await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    assert r.status_code == 200
    d = {x["temp_id"]: x for x in r.json()["data"]["drafts"]}
    assert (d["a4"]["placement"], d["a4"]["start_at"][11:16], d["a4"]["end_at"][11:16], d["a4"]["time_certainty"]) == ("placed", "08:30", "09:15", "stated")
    assert (d["a5"]["placement"], d["a5"]["start_at"][11:16], d["a5"]["end_at"][11:16], d["a5"]["duration_minutes"], d["a5"]["time_certainty"]) == ("placed", "09:15", "12:30", 195, "inferred")
    out = r.json()["data"]
    assert out["questions"] == [] and out["blocking"] == [] and out["summary"]["gap_count"] == 1 and out["summary"]["not_mentioned_minutes"] == 30
    assert d["a4"]["confidence"] > 0.49 and d["a5"]["band"] != "low" or d["a5"]["confidence"] > 0.49                    # the cap lifts once resolved


async def test_keeping_the_meeting_as_some_time_leaves_product_b_asking_for_itself(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    out = (await answer(client, p, e["id"], job_id, "start_time:a4", "unplaced")).json()["data"]
    d = {x["temp_id"]: x for x in out["drafts"]}
    assert d["a4"]["placement"] == "unplaced" and d["a4"]["duration_minutes"] == 45
    assert [q["id"] for q in out["questions"]] == ["start_time:a5"]                                                        # now a5 asks, instead of hanging forever
    final = (await answer(client, p, e["id"], job_id, "start_time:a5", "custom:15:00")).json()["data"]
    assert by_title(final["drafts"])["Product B work"]["start_at"][11:16] == "09:30" and final["questions"] == []


async def test_invalid_answers_are_refused(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    for qid, value in (("start_time:zzz", "14:00"), ("start_time:a4", "99:99"), ("start_time:a4", "banana")):
        r = await answer(client, p, e["id"], job_id, qid, value)
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_ANSWER", (qid, value)


async def test_commit_confirms_everything_in_one_transaction_and_feeds_the_calendar(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id, out = await commit_all(client, db, p, e["id"])
    assert len(out["activities"]) == 5 and out["created_tags"] == [] and out["replaced"] == []
    assert all(a["status"] == "confirmed" and a["origin"] == "ai" and a["journal_entry_id"] == e["id"] for a in out["activities"])
    assert (await client.get(f"{API}/journal-entries/{e['id']}", headers=p.headers)).json()["data"]["status"] == "confirmed"
    assert (await db.execute(text("SELECT sum(minutes) FROM activity_day_slices"))).scalar_one() == 510                       # 60+150+60+45+195
    day = (await client.get(f"{API}/timeline?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]["days"][0]
    assert [b["title"] for b in day["blocks"]] == ["Research new AI feature", "Product A: API debugging and database fixes", "Lunch", "Meeting", "Product B work"]
    assert (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'draft'"))).scalar_one() == 0
    bug = next(a for a in out["activities"] if a["title"].startswith("Product A"))
    assert [t["name"] for t in bug["tags"]] == ["bug"] and bug["tags"][0]["source"] == "rule"                                   # the unkept new tag was not created
    detail = (await client.get(f"{API}/activities/{bug['id']}", headers=p.headers)).json()["data"]
    assert detail["source"]["quote"].startswith("After that, worked on Product A") and "Spent an hour" in detail["source"]["context_before"]
    events = (await client.get(f"{API}/activities/{bug['id']}/events", headers=p.headers)).json()["data"]
    assert [x["event_type"] for x in events] == ["created", "approved"] and events[0]["actor"] == "ai"
    from app.repositories.activities import ActivitiesRepository

    assert await ActivitiesRepository(db, uuid.UUID(p.id)).slice_invariant_violations() == []


async def test_ac021_the_same_commit_sent_twice_creates_activities_once(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    one = await commit(client, p, e["id"], job_id, key="same-key")
    two = await commit(client, p, e["id"], job_id, key="same-key")
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    assert (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'confirmed'"))).scalar_one() == 5
    other = await commit(client, p, e["id"], job_id, key="same-key", replace_previous=True)
    assert other.status_code == 422 and other.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    assert (await client.post(f"{API}/journal-entries/{e['id']}/review/commit", headers=p.headers, json={"job_id": job_id})).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_ac019_excluded_rows_never_become_activities_and_are_recorded_as_rejected(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    drafts = (await review(client, p, e["id"]))["drafts"]
    skip = {d["temp_id"] for d in drafts[:3]}
    acts = [{"draft_id": d["id"], "include": d["temp_id"] not in skip} for d in drafts]
    r = await commit(client, p, e["id"], job_id, activities=acts)
    assert r.status_code == 200 and len(r.json()["data"]["activities"]) == 2
    assert (await db.execute(text("SELECT count(*) FROM activities"))).scalar_one() == 2
    rejected = (await db.execute(text("SELECT jsonb_array_length(parsed_response->'rejected') FROM ai_processing_jobs WHERE id = :i"), {"i": job_id})).scalar_one()
    assert rejected == 3


async def test_commit_is_refused_while_a_duration_is_missing(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    r = await commit(client, p, e["id"], job_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_BLOCKED"
    blockers = r.json()["error"]["details"]["blockers"]
    assert [b["reason"] for b in blockers] == ["MISSING_DURATION"] and (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'confirmed'"))).scalar_one() == 0
    drafts = (await review(client, p, e["id"]))["drafts"]
    a5 = next(d for d in drafts if d["temp_id"] == "a5")
    ok = await commit(client, p, e["id"], job_id, activities=[{"draft_id": a5["id"], "include": False}])
    assert ok.status_code == 200 and len(ok.json()["data"]["activities"]) == 4                                               # the unplaced meeting is allowed: it has a duration
    meeting = next(a for a in ok.json()["data"]["activities"] if a["title"] == "Meeting")
    assert meeting["placement"] == "unplaced" and meeting["duration_minutes"] == 45


async def test_ac018_an_overlap_with_a_confirmed_activity_blocks_the_commit_and_names_it(client, db):
    p = await signup(client)
    existing = (await log(client, p, "Client call", "2025-06-02", "10:00", "11:00", "Meetings")).json()["data"]
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    rv = await review(client, p, e["id"])
    assert sorted((c["other_id"], c["overlap_minutes"]) for c in rv["conflicts"]) == [(existing["id"], 30), (existing["id"], 30)]   # a1 by 30 min, a2 by 30 min
    assert any(b["reason"] == "OVERLAP" for b in rv["blocking"])
    r = await commit(client, p, e["id"], job_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_BLOCKED"
    assert {b["other_title"] for b in r.json()["error"]["details"]["blockers"] if b["reason"] == "OVERLAP"} == {"Client call"}
    assert (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'confirmed'"))).scalar_one() == 1       # all or nothing


@pytest.mark.parametrize("action", ["replace_existing", "trim_new", "keep_unplaced"])
async def test_every_conflict_resolution_leaves_a_consistent_calendar(client, db, action):
    p = await signup(client)
    existing = (await log(client, p, "Client call", "2025-06-02", "10:00", "11:00", "Meetings")).json()["data"]
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    drafts = {d["temp_id"]: d for d in (await review(client, p, e["id"]))["drafts"]}
    res = [{"draft_id": drafts[t]["id"], "action": action, "existing_id": existing["id"]} for t in ("a1", "a2")]
    r = await commit(client, p, e["id"], job_id, conflict_resolutions=res)
    assert r.status_code == 200, r.text
    from app.repositories.activities import ActivitiesRepository

    assert await ActivitiesRepository(db, uuid.UUID(p.id)).slice_invariant_violations() == []
    day = (await client.get(f"{API}/timeline?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]["days"][0]
    placed = sorted((b["start_at"], b["end_at"], b["title"]) for b in day["blocks"])
    assert all(placed[i][1] <= placed[i + 1][0] for i in range(len(placed) - 1))                                           # nothing overlaps
    titles = {b["title"] for b in day["blocks"]}
    if action == "replace_existing":
        assert "Client call" not in titles and (await client.get(f"{API}/activities/{existing['id']}", headers=p.headers)).status_code == 404
    if action == "keep_unplaced":
        unplaced = {u["title"] for u in day["unplaced"]}
        assert {"Research new AI feature"} <= unplaced and "Client call" in titles


async def test_edits_tags_new_tags_tasks_and_transitions(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    rv = await review(client, p, e["id"])
    d = by_title(rv["drafts"])
    gap = rv["gaps"][0]
    edits = [{"draft_id": d["Research new AI feature"]["id"], "edits": {"title": "Research the AI feature", "category_id": p.cats["Learning"], "tag_ids": [p.tags["p0"]],
                                                                      "start_at": "2025-06-02T09:30:00+05:30", "end_at": "2025-06-02T10:15:00+05:30", "description": "Mostly papers"}},
             {"draft_id": d["Product B work"]["id"], "edits": {"new_task_title": "Ship Product B"}}]
    r = await commit(client, p, e["id"], job_id, activities=edits, new_tags=[{"draft_id": d["Product B work"]["id"], "name": "product-b", "keep": True},
                                                                               {"draft_id": d["Product A: API debugging and database fixes"]["id"], "name": "product-a", "keep": False}],
                     transitions=[{"start_at": gap["start_at"], "end_at": gap["end_at"]}])
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["created_tags"] == ["product-b"] and out["created_tasks"] == ["Ship Product B"]
    res = by_title(out["activities"])
    a1 = res["Research the AI feature"]
    assert (a1["duration_minutes"], a1["category"]["name"], a1["user_edited"], a1["description"], [t["name"] for t in a1["tags"]]) == (45, "Learning", True, "Mostly papers", ["p0"])
    assert a1["tags"][0]["source"] == "user" and a1["time_certainty"] == "stated"
    b = res["Product B work"]
    assert [t["name"] for t in b["tags"]] == ["product-b"] and b["task_id"] is not None and b["user_edited"] is False
    tr = res["Transition"]
    assert tr["category"]["name"] == "Transitions" and tr["origin"] == "manual" and tr["duration_minutes"] == 30
    assert "product-a" not in {t["name"] for t in (await client.get(f"{API}/tags", headers=p.headers)).json()["data"]}


async def test_transitions_need_a_transition_category(client, db):
    p = await signup(client, seed="empty")
    e = (await create_entry(client, p, "I worked from 9 to 10.")).json()["data"]
    prov = FixtureProvider({"schema_version": "1", "entry_summary": "Work", "activities": [{"temp_id": "a1", "order": 1, "title": "Work", "source_quote": "worked from 9 to 10", "category_id": p.cats["Work"],
                                                                                         "time_ref": {"kind": "range", "start": {"hour": 9}, "end": {"hour": 10}, "quote": "9 to 10"}, "confidence": {"overall": 0.9, "time": 0.9, "category": 0.9}}]})
    job_id = await submit(client, db, p, e["id"], prov)
    r = await commit(client, p, e["id"], job_id, transitions=[{"start_at": "2025-06-02T15:00:00+05:30", "end_at": "2025-06-02T15:30:00+05:30"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_TRANSITION_CATEGORY"


async def test_ac026_a_likely_duplicate_arrives_unchecked_with_a_link_to_the_original(client, db):
    p = await signup(client)
    first = (await create_entry(client, p, TEXT)).json()["data"]
    await commit_all(client, db, p, first["id"])
    second = (await create_entry(client, p, TEXT, start="09:00", end="18:00")).json()["data"]
    await submit(client, db, p, second["id"], FixtureProvider(prd_response(p)))
    rv = await review(client, p, second["id"])
    dups = [d for d in rv["drafts"] if d["duplicate_of"]]
    assert dups and all(d["include"] is False and "possible_duplicate" in d["flags"] for d in dups)
    lunch = next(d for d in rv["drafts"] if d["title"] == "Lunch")
    original = (await client.get(f"{API}/activities?q=Lunch", headers=p.headers)).json()["data"][0]
    assert lunch["duplicate_of"]["id"] == original["id"] and lunch["include"] is False
    assert rv["summary"]["activity_count"] == len([d for d in rv["drafts"] if d["include"]])


async def test_ac023_regenerating_with_replace_keeps_the_activities_the_person_edited(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    _, first = await commit_all(client, db, p, e["id"])
    lunch = next(a for a in first["activities"] if a["title"] == "Lunch")
    await client.patch(f"{API}/activities/{lunch['id']}", headers=p.headers, json={"version": lunch["version"], "title": "Long lunch"})
    job2 = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p, variant="b")), regenerate=True, hint="be careful with titles")
    rv = await review(client, p, e["id"])
    assert rv["job"]["id"] == job2 and {c["title"] for c in rv["replace_candidates"] if c["user_edited"]} == {"Long lunch"}
    assert (await db.execute(text("SELECT user_hint FROM ai_processing_jobs WHERE id = :i"), {"i": job2})).scalar_one() == "be careful with titles"
    await answer(client, p, e["id"], job2, "start_time:a4", "14:00")
    drafts = {d["temp_id"]: d for d in (await review(client, p, e["id"]))["drafts"]}
    # the earlier activities are still on the calendar, so everything overlaps unless the old ones are replaced
    blocked = await commit(client, p, e["id"], job2)
    assert blocked.status_code == 409
    skip_lunch = [{"draft_id": drafts["a3"]["id"], "include": False}]                                                      # the edited lunch stays, so skip its twin
    r = await commit(client, p, e["id"], job2, replace_previous=True, activities=skip_lunch)
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert len(out["replaced"]) == 4 and out["kept_edited"] == [lunch["id"]]
    live = {a["title"] for a in (await client.get(f"{API}/activities?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]}
    assert live == {"Long lunch", "Research new AI feature (v2)", "Product A: API debugging and database fixes (v2)", "Meeting (v2)", "Product B work (v2)"}
    assert (await commit(client, p, e["id"], str(uuid.uuid4()))).status_code == 404                                        # an unknown job id


async def test_committing_an_older_run_after_a_newer_one_is_refused(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    old_job = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await submit(client, db, p, e["id"], FixtureProvider(prd_response(p, variant="b")), regenerate=True)
    r = await commit(client, p, e["id"], old_job)
    assert r.status_code == 409 and r.json()["error"]["code"] == "JOB_NOT_LATEST"
    assert (await db.execute(text("SELECT count(*) FROM activities WHERE status = 'draft'"))).scalar_one() == 5            # only the newest run's drafts exist


async def test_the_ideal_day_preview_maps_each_draft_to_its_allocation(client, db):
    p = await signup(client)
    await client.put(f"{API}/ideal/day", headers=p.headers, json=day_body(p, "2025-01-01"))
    await log(client, p, "Gym", "2025-06-02", "07:00", "08:00", "Entertainment")
    e = (await create_entry(client, p, TEXT)).json()["data"]
    await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    rv = await review(client, p, e["id"])
    ideal = rv["ideal"]
    assert ideal["date"] == "2025-06-02" and sum(r["target"] for r in ideal["rows"]) == 1440
    row = {r["name"]: r for r in ideal["rows"]}
    assert row["Entertainment"]["actual"] == 60                                                                            # confirmed time only; drafts are not counted yet
    deep = next(d for d in rv["drafts"] if d["title"] == "Lunch")
    assert deep["ideal_row_id"] == row["Meals & chores"]["category_id"]


async def test_trim_existing_shortens_the_other_activity_to_make_room(client, db):
    p = await signup(client)
    existing = (await log(client, p, "Early standup", "2025-06-02", "09:00", "10:00", "Meetings")).json()["data"]   # overlaps a1 (09:30-10:30) by 30 min
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    a1 = next(d for d in (await review(client, p, e["id"]))["drafts"] if d["temp_id"] == "a1")
    r = await commit(client, p, e["id"], job_id, conflict_resolutions=[{"draft_id": a1["id"], "action": "trim_existing", "existing_id": existing["id"]}])
    assert r.status_code == 200, r.text
    call = (await client.get(f"{API}/activities/{existing['id']}", headers=p.headers)).json()["data"]
    assert (call["duration_minutes"], call["user_edited"], call["end_at"][11:16]) == (30, True, "04:00")             # 09:00-09:30 IST
    from app.repositories.activities import ActivitiesRepository

    assert await ActivitiesRepository(db, uuid.UUID(p.id)).slice_invariant_violations() == []


async def test_one_existing_activity_cannot_be_trimmed_from_both_sides(client, db):
    p = await signup(client)
    existing = (await log(client, p, "Client call", "2025-06-02", "10:00", "11:00", "Meetings")).json()["data"]
    e = (await create_entry(client, p, TEXT)).json()["data"]
    job_id = await submit(client, db, p, e["id"], FixtureProvider(prd_response(p)))
    await answer(client, p, e["id"], job_id, "start_time:a4", "14:00")
    drafts = {d["temp_id"]: d for d in (await review(client, p, e["id"]))["drafts"]}
    res = [{"draft_id": drafts[t]["id"], "action": "trim_existing", "existing_id": existing["id"]} for t in ("a1", "a2")]
    r = await commit(client, p, e["id"], job_id, conflict_resolutions=res)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_BLOCKED"                                    # honest: no room can be made
    assert (await client.get(f"{API}/activities/{existing['id']}", headers=p.headers)).json()["data"]["duration_minutes"] == 60   # untouched on failure
