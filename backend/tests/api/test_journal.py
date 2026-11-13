import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.ai.providers import ProviderTransientError
from app.ai.providers.fake_provider import FixtureProvider
from app.core.config import get_settings
from tests.ai_fixtures import TEXT, prd_response
from tests.factories import at, create_entry, idem, signup, submit

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def test_create_entry_is_a_draft_with_a_local_date_and_no_revision_rows_yet(client, db):
    p = await signup(client)
    r = await create_entry(client, p, TEXT)
    e = r.json()["data"]
    assert r.status_code == 201 and e["status"] == "draft" and e["revision"] == 1 and e["version"] == 1 and e["entry_date"] == "2025-06-02"
    assert (await db.execute(text("SELECT count(*) FROM journal_entry_revisions"))).scalar_one() == 0   # drafts autosave without history


async def test_window_rules(client):
    p = await signup(client)
    long = await client.post(f"{API}/journal-entries", headers=p.headers, json={"raw_text": "x", "covers_start_at": at("2025-06-02", "00:00"), "covers_end_at": at("2025-06-03", "01:00"), "timezone": "Asia/Kolkata"})
    assert long.status_code == 422 and long.json()["error"]["code"] == "WINDOW_TOO_LONG"                        # AC-008
    exactly = await client.post(f"{API}/journal-entries", headers=p.headers, json={"raw_text": "x", "covers_start_at": at("2025-06-02", "00:00"), "covers_end_at": at("2025-06-03", "00:00"), "timezone": "Asia/Kolkata"})
    assert exactly.status_code == 201
    future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    f = await client.post(f"{API}/journal-entries", headers=p.headers, json={"raw_text": "x", "covers_start_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(), "covers_end_at": future})
    assert f.status_code == 422 and f.json()["error"]["code"] == "WINDOW_IN_FUTURE"
    back = await client.post(f"{API}/journal-entries", headers=p.headers, json={"raw_text": "x", "covers_start_at": at("2025-06-02", "10:00"), "covers_end_at": at("2025-06-02", "09:00")})
    assert back.status_code == 422
    for bad in ("", "x" * 10_001):
        assert (await create_entry(client, p, bad)).status_code == 422


async def test_ac010_overlapping_windows_warn_but_still_save(client, db):
    p = await signup(client)
    first = (await create_entry(client, p, "morning stuff", start="09:00", end="13:00")).json()["data"]
    await client.patch(f"{API}/journal-entries/{first['id']}", headers=p.headers, json={"version": 1, "title": "Morning"})
    await submit(client, db, p, first["id"], FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []}))
    second = await create_entry(client, p, "later stuff", start="12:00", end="18:00")
    assert second.status_code == 201
    assert [o["id"] for o in second.json()["meta"]["overlaps"]] == [first["id"]]


async def test_ac007_revision_one_is_the_first_submitted_text_forever(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, "first draft words")).json()["data"]
    r = await client.patch(f"{API}/journal-entries/{e['id']}", headers=p.headers, json={"version": 1, "raw_text": "the text I actually submitted"})   # autosave
    assert r.json()["data"]["revision"] == 1 and (await db.execute(text("SELECT count(*) FROM journal_entry_revisions"))).scalar_one() == 0
    await submit(client, db, p, e["id"], FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []}))
    r = await client.patch(f"{API}/journal-entries/{e['id']}", headers=p.headers, json={"version": 2, "raw_text": "an edited version"})
    assert r.json()["data"]["revision"] == 2 and r.json()["data"]["raw_text"] == "an edited version"
    revs = (await client.get(f"{API}/journal-entries/{e['id']}/revisions", headers=p.headers)).json()["data"]
    assert [(x["revision"], x["raw_text"]) for x in revs] == [(1, "the text I actually submitted"), (2, "an edited version")]
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):  # the table is append-only at the database level
        await db.execute(text("UPDATE journal_entry_revisions SET raw_text = 'tampered' WHERE revision = 1"))


async def test_optimistic_lock_and_stale_jobs(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, "hello there")).json()["data"]
    ok = await client.patch(f"{API}/journal-entries/{e['id']}", headers=p.headers, json={"version": 1, "raw_text": "hello again"})
    stale = await client.patch(f"{API}/journal-entries/{e['id']}", headers=p.headers, json={"version": 1, "raw_text": "other tab"})
    assert ok.status_code == 200 and stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    job_id = await submit(client, db, p, e["id"], FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []}))
    await client.patch(f"{API}/journal-entries/{e['id']}", headers=p.headers, json={"version": 2, "raw_text": "edited after the run"})
    assert (await client.get(f"{API}/ai-jobs/{job_id}", headers=p.headers)).json()["data"]["is_stale"] is True


async def test_history_filters_search_and_cursor_pagination(client, db):
    p = await signup(client)
    ids = []
    for i, d in enumerate(("2025-06-01", "2025-06-02", "2025-06-03")):
        e = (await create_entry(client, p, f"entry number {i} about {'gardening' if i == 1 else 'work'}", day=d)).json()["data"]
        ids.append(e["id"])
    r = await client.get(f"{API}/journal-entries?limit=2", headers=p.headers)
    assert [x["entry_date"] for x in r.json()["data"]] == ["2025-06-03", "2025-06-02"] and r.json()["meta"]["next_cursor"]
    r2 = await client.get(f"{API}/journal-entries?limit=2&cursor={r.json()['meta']['next_cursor']}", headers=p.headers)
    assert [x["entry_date"] for x in r2.json()["data"]] == ["2025-06-01"] and r2.json()["meta"]["next_cursor"] is None
    assert [x["id"] for x in (await client.get(f"{API}/journal-entries?q=gardening", headers=p.headers)).json()["data"]] == [ids[1]]
    assert [x["entry_date"] for x in (await client.get(f"{API}/journal-entries?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]] == ["2025-06-02"]
    assert (await client.get(f"{API}/journal-entries?status=confirmed", headers=p.headers)).json()["data"] == []
    s = (await client.get(f"{API}/journal-entries", headers=p.headers)).json()["data"][0]
    assert s["title"].startswith("entry number 2") and s["word_count"] == 5 and s["activity_count"] == 0


async def test_ai_disabled_saves_a_manual_entry_and_creates_no_job_ac024(client, db):
    p = await signup(client)
    await client.patch(f"{API}/users/me/preferences", headers=p.headers, json={"ai_enabled": False})
    e = (await create_entry(client, p, TEXT)).json()["data"]
    r = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "AI_DISABLED" and r.json()["error"]["details"]["entry_id"] == e["id"]
    assert (await db.execute(text("SELECT count(*) FROM ai_processing_jobs"))).scalar_one() == 0
    assert (await client.get(f"{API}/journal-entries/{e['id']}", headers=p.headers)).json()["data"]["status"] == "manual"


async def test_process_needs_an_idempotency_key_and_replays_safely(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    assert (await client.post(f"{API}/journal-entries/{e['id']}/process", headers=p.headers, json={})).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    key = idem()
    one = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **key}, json={})
    two = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **key}, json={})
    assert one.status_code == two.status_code == 202 and one.json() == two.json()
    assert (await db.execute(text("SELECT count(*) FROM ai_processing_jobs"))).scalar_one() == 1
    clash = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **key}, json={"regenerate": True})
    assert clash.status_code == 422 and clash.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    busy = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "ENTRY_BUSY"          # queued: not finished yet


async def test_the_same_text_within_ten_minutes_reuses_the_job(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    empty = FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []})
    first = await submit(client, db, p, e["id"], empty)
    again = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    assert again.json()["data"]["job_id"] == first                                               # FR-055
    regen = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={"regenerate": True})
    assert regen.json()["data"]["job_id"] != first and (await db.execute(text("SELECT count(*) FROM ai_processing_jobs"))).scalar_one() == 2


async def test_daily_limit_returns_429_with_reset_time_and_regenerations_are_capped(client, db, monkeypatch):
    p = await signup(client)
    monkeypatch.setattr(get_settings(), "ai_daily_job_limit", 2)
    empty = FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []})
    e1 = (await create_entry(client, p, "one", day="2025-06-02")).json()["data"]
    e2 = (await create_entry(client, p, "two", day="2025-06-03")).json()["data"]
    e3 = (await create_entry(client, p, "three", day="2025-06-04")).json()["data"]
    await submit(client, db, p, e1["id"], empty)
    await submit(client, db, p, e2["id"], empty)
    r = await client.post(f"{API}/journal-entries/{e3['id']}/process", headers={**p.headers, **idem()}, json={})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) > 0 and "Daily limit" in r.json()["error"]["message"]
    st = (await client.get(f"{API}/ai/status", headers=p.headers)).json()["data"]
    assert st["used_today"] == 2 and st["daily_limit"] == 2 and st["enabled"] is True


async def test_regeneration_is_limited_per_entry_per_day(client, db, monkeypatch):
    p = await signup(client)
    monkeypatch.setattr(get_settings(), "ai_regenerations_per_day", 1)
    empty = FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []})
    e = (await create_entry(client, p, "words")).json()["data"]
    await submit(client, db, p, e["id"], empty)
    await submit(client, db, p, e["id"], empty, regenerate=True)                                  # the one allowed regeneration
    r = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={"regenerate": True})
    assert r.status_code == 429 and r.json()["error"]["code"] == "AI_REGEN_LIMIT"


# --------------------------------------------------------------------------------------------------------- worker behaviour
class Flaky:
    name, model = "flaky", "flaky-1"

    def __init__(self, error):
        self.error, self.calls = error, 0

    async def generate_structured(self, request):
        self.calls += 1
        raise self.error


async def test_transient_errors_retry_with_backoff_then_fail_but_keep_the_text(client, db):
    from app.workers.tasks_ai import run_job

    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    r = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    job_id = uuid.UUID(r.json()["data"]["job_id"])
    prov = Flaky(ProviderTransientError("429"))
    for attempt, _delay in ((1, 2), (2, 8)):
        await run_job(db, job_id, prov)
        row = (await db.execute(text("SELECT status::text, attempts, queued_at > now() FROM ai_processing_jobs WHERE id = :i"), {"i": job_id})).one()
        assert row[0] == "queued" and row[1] == attempt and row[2] is True                          # re-queued for later (2 s, then 8 s)
        await db.execute(text("UPDATE ai_processing_jobs SET queued_at = now() WHERE id = :i"), {"i": job_id})
    await run_job(db, job_id, prov)
    job = (await client.get(f"{API}/ai-jobs/{job_id}", headers=p.headers)).json()["data"]
    assert job["status"] == "failed" and job["error_code"] == "PROVIDER_UNAVAILABLE" and job["attempts"] == 3 and prov.calls == 3
    entry = (await client.get(f"{API}/journal-entries/{e['id']}", headers=p.headers)).json()["data"]
    assert entry["status"] == "failed" and entry["raw_text"] == TEXT                                # AC-017: nothing lost
    again = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={"regenerate": True})
    assert again.status_code == 202                                                                   # Retry works


async def test_ac017_invalid_json_twice_fails_the_job_and_leaves_the_entry_text(client, db):
    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    bad = FixtureProvider([{"schema_version": "1", "activities": [{"temp_id": "a1"}]}] * 2)
    job_id = await submit(client, db, p, e["id"], bad)
    job = (await client.get(f"{API}/ai-jobs/{job_id}", headers=p.headers)).json()["data"]
    assert job["status"] == "failed" and job["error_code"] == "INVALID_MODEL_OUTPUT" and len(bad.requests) == 2
    assert (await client.get(f"{API}/journal-entries/{e['id']}", headers=p.headers)).json()["data"]["raw_text"] == TEXT


async def test_queue_claims_each_job_once_and_requeues_stuck_ones(client, db):
    from app.workers.runner import claim_next, requeue_stuck

    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    r = await client.post(f"{API}/journal-entries/{e['id']}/process", headers={**p.headers, **idem()}, json={})
    job_id = uuid.UUID(r.json()["data"]["job_id"])
    claimed = await claim_next(db)
    assert claimed.id == job_id and claimed.status.value == "running" and claimed.attempts == 1
    assert await claim_next(db) is None                                                              # nobody else gets it
    await db.execute(text("UPDATE ai_processing_jobs SET started_at = now() - interval '6 minutes' WHERE id = :i"), {"i": job_id})
    db.expire_all()
    assert await requeue_stuck(db) == 1
    assert (await db.execute(text("SELECT status::text FROM ai_processing_jobs WHERE id = :i"), {"i": job_id})).scalar_one() == "queued"
    await db.execute(text("UPDATE ai_processing_jobs SET status='running', attempts = 3, started_at = now() - interval '6 minutes' WHERE id = :i"), {"i": job_id})
    db.expire_all()  # the raw UPDATE bypassed the ORM's cached copy
    await requeue_stuck(db)
    row = (await db.execute(text("SELECT status::text, error_code FROM ai_processing_jobs WHERE id = :i"), {"i": job_id})).one()
    assert row == ("failed", "TIMED_OUT")


# --------------------------------------------------------------------------------------------------------- stats
async def _confirmed_entry(db, user_id: str, d, tz="UTC"):
    start = datetime(d.year, d.month, d.day, 9, tzinfo=UTC)
    await db.execute(text("INSERT INTO journal_entries (user_id, entry_date, covers_start_at, covers_end_at, timezone, raw_text, text_hash, status) "
                          "VALUES (:u, :d, :s, :e, :tz, 'x', 'h', 'confirmed')"), {"u": user_id, "d": d, "s": start, "e": start + timedelta(hours=8), "tz": tz})


async def test_ac014_streak_survives_a_day_without_an_entry_yet(client, db):
    p = await signup(client, tz="UTC")
    today = datetime.now(UTC).date()
    for i in range(1, 24):
        await _confirmed_entry(db, p.id, today - timedelta(days=i))
    assert (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]["streak_days"] == 23
    await _confirmed_entry(db, p.id, today)
    assert (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]["streak_days"] == 24
    await db.execute(text("DELETE FROM journal_entries WHERE entry_date = :d"), {"d": today - timedelta(days=5)})
    assert (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]["streak_days"] == 5   # a hole ends the streak


async def test_ac013_the_short_yesterday_nudge_reports_the_biggest_gap(client, db):
    p = await signup(client, tz="UTC")
    y = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    r = await client.post(f"{API}/activities", headers=p.headers, json={"title": "Long day", "category_id": p.cats["Deep work"], "start_at": f"{y}T00:00:00Z", "end_at": f"{y}T19:30:00Z"})
    assert r.status_code == 201
    gap = (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]["yesterday_gap"]
    assert gap["minutes"] == 270 and gap["date"] == y and gap["start_at"].startswith(f"{y}T19:30") and gap["end_at"].startswith(f"{(datetime.now(UTC)).date().isoformat()}T00:00")
    await client.post(f"{API}/activities", headers=p.headers, json={"title": "Evening", "category_id": p.cats["Entertainment"], "start_at": f"{y}T19:30:00Z", "end_at": f"{y}T23:55:00Z"})
    assert (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]["yesterday_gap"] is None    # within tolerance


async def test_a_new_account_gets_no_nudge_and_no_percentage(client):
    p = await signup(client, tz="UTC")
    s = (await client.get(f"{API}/journal-entries/stats", headers=p.headers)).json()["data"]
    assert s == {"streak_days": 0, "entries_per_day_30d": 0.0, "full_days_pct_30d": None, "yesterday_gap": None}


# --------------------------------------------------------------------------------------------------------- delete and isolation
async def test_ac012_deleting_an_entry_asks_what_to_do_with_its_activities(client, db):
    from tests.api.test_review import commit_all

    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    await commit_all(client, db, p, e["id"])
    n = len((await client.get(f"{API}/activities?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"])
    assert n == 5
    need = await client.delete(f"{API}/journal-entries/{e['id']}", headers=p.headers)
    assert need.status_code == 422 and need.json()["error"]["code"] == "ACTIVITIES_CHOICE_REQUIRED"
    assert (await client.delete(f"{API}/journal-entries/{e['id']}?activities=delete", headers=p.headers)).status_code == 204
    assert (await client.get(f"{API}/activities?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"] == []
    assert (await db.execute(text("SELECT count(*) FROM activity_day_slices"))).scalar_one() == 0
    assert (await client.get(f"{API}/journal-entries/{e['id']}", headers=p.headers)).status_code == 404


async def test_keep_leaves_the_activities_and_marks_them_manually_owned(client, db):
    from tests.api.test_review import commit_all

    p = await signup(client)
    e = (await create_entry(client, p, TEXT)).json()["data"]
    await commit_all(client, db, p, e["id"])
    assert (await client.delete(f"{API}/journal-entries/{e['id']}?activities=keep", headers=p.headers)).status_code == 204
    acts = (await client.get(f"{API}/activities?from=2025-06-02&to=2025-06-02", headers=p.headers)).json()["data"]
    assert len(acts) == 5 and all(a["user_edited"] for a in acts)


async def test_entries_jobs_and_reviews_belong_to_their_owner(client, db):
    a, b = await signup(client), await signup(client)
    e = (await create_entry(client, a, TEXT)).json()["data"]
    job_id = await submit(client, db, a, e["id"], FixtureProvider(prd_response(a)))
    h = b.headers
    for call in (client.get(f"{API}/journal-entries/{e['id']}", headers=h), client.patch(f"{API}/journal-entries/{e['id']}", headers=h, json={"version": 1, "title": "x"}),
                 client.delete(f"{API}/journal-entries/{e['id']}", headers=h), client.get(f"{API}/journal-entries/{e['id']}/revisions", headers=h),
                 client.post(f"{API}/journal-entries/{e['id']}/process", headers={**h, **idem()}, json={}), client.get(f"{API}/ai-jobs/{job_id}", headers=h),
                 client.get(f"{API}/journal-entries/{e['id']}/review", headers=h),
                 client.post(f"{API}/journal-entries/{e['id']}/review/answers", headers=h, json={"job_id": job_id, "question_id": "x", "value": "14:00"}),
                 client.post(f"{API}/journal-entries/{e['id']}/review/commit", headers={**h, **idem()}, json={"job_id": job_id})):
        r = await call
        assert r.status_code == 404, (r.request.url, r.text)
    assert (await client.get(f"{API}/journal-entries", headers=h)).json()["data"] == []


async def test_ac027_neither_the_model_payload_nor_the_logs_carry_the_journal(client, db, capsys):
    p = await signup(client)
    secret = "zebrafish-quartz-9931"
    e = (await create_entry(client, p, f"I wrote about {secret} from 9 to 10 in the morning.")).json()["data"]
    prov = FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": []})
    await submit(client, db, p, e["id"], prov)
    sent = prov.requests[0].system + prov.requests[0].user
    assert secret in sent                                    # the entry text itself is what the model must read
    for forbidden in (p.email, "Test User", p.id):
        assert forbidden not in sent
    assert secret not in capsys.readouterr().out             # nothing the API logged contains the journal words
