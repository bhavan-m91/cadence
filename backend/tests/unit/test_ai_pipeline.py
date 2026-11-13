import uuid
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.ai.context_builder import CategoryInfo, build_context
from app.ai.extraction_pipeline import Existing, ExtractionFailed, PipelineInput, run_extraction
from app.ai.providers.fake_provider import FakeProvider, FixtureProvider
from app.ai.quote_verifier import time_supported, verify_quote
from app.ai.tag_matcher import RuleInfo, TagInfo, match_tags, phrase_in
from app.ai.task_matcher import OpenTask, match_task
from app.core.time import parse_local

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 13)
TEXT = ("Started my day at around 9:30. Spent an hour researching how to implement the new AI feature. After that, worked on Product A until 1 PM, "
        "mainly debugging the API and fixing some database issues. Had lunch from 1 to 2. In the afternoon, attended a meeting for about 45 minutes "
        "and then worked on Product B until 6.")

DEEP, MEET, MEALS, WORK_ROOT, SLEEP = (uuid.uuid4() for _ in range(5))
CATS = [
    CategoryInfo(WORK_ROOT, "Work", "Work", "work"), CategoryInfo(DEEP, "Deep work", "Work › Deep work", "work", counts_as_focus=True),
    CategoryInfo(MEET, "Meetings", "Work › Meetings", "work"), CategoryInfo(MEALS, "Meals & chores", "Personal › Meals & chores", "personal"),
    CategoryInfo(SLEEP, "Sleep", "Sleep", "sleep"),
]
T_RESEARCH, T_A, T_BUG, T_MEET, T_B, T_SOCIAL = (uuid.uuid4() for _ in range(6))
TAGS = [TagInfo(T_RESEARCH, "research"), TagInfo(T_A, "product-a"), TagInfo(T_BUG, "bug", aliases=["defect"]), TagInfo(T_MEET, "meetings"),
        TagInfo(T_B, "product-b"), TagInfo(T_SOCIAL, "social-media")]


def make_input(text=TEXT, rules=None, existing=None, h0=9, h1=18, tags=None):
    return PipelineInput(text=text, window_start=parse_local(DAY, time(h0), IST), window_end=parse_local(DAY, time(h1), IST), tz=IST, tz_name="Asia/Kolkata",
                         now=datetime(2026, 11, 13, 12, 30, tzinfo=UTC), categories=CATS, tags=tags or TAGS, rules=rules or [], open_tasks=[],
                         existing=existing or [], gap_min_minutes=10)


def tod(h, m=0, mer=None):
    return {"hour": h, "minute": m, "meridiem": mer}


def prd_response():
    def act(i, title, quote, cat, ref, tags=(), conf=(0.9, 0.9, 0.9), flags=()):
        return {"temp_id": f"a{i}", "order": i, "title": title, "description": None, "source_quote": quote, "category_id": str(cat), "time_ref": ref,
                "tags": [{"tag_id": str(t), "name": n, "reason": n, "confidence": 0.9} for t, n in tags], "task": None, "location_type": None,
                "confidence": dict(zip(("overall", "time", "category"), conf)), "flags": list(flags)}
    return {"schema_version": "1", "entry_summary": "Research, Product A debugging, lunch, a meeting and Product B", "activities": [
        act(1, "Research new AI feature", "Started my day at around 9:30. Spent an hour researching how to implement the new AI feature", DEEP,
            {"kind": "range", "start": tod(9, 30), "duration_minutes": 60, "approximate": True, "quote": "around 9:30 ... an hour"}, [(T_RESEARCH, "research")], (0.9, 0.85, 0.8)),
        act(2, "Product A: API debugging and database fixes", "After that, worked on Product A until 1 PM, mainly debugging the API and fixing some database issues", DEEP,
            {"kind": "range", "start_anchor": "previous_end", "end": tod(1, 0, "pm"), "quote": "After that ... until 1 PM"}, [(T_A, "product-a"), (T_BUG, "bug")]),
        act(3, "Lunch", "Had lunch from 1 to 2", MEALS, {"kind": "range", "start": tod(1), "end": tod(2), "quote": "from 1 to 2"}, conf=(0.95, 0.9, 0.95)),
        act(4, "Meeting", "In the afternoon, attended a meeting for about 45 minutes", MEET,
            {"kind": "vague", "duration_minutes": 45, "approximate": True, "window": {"label": "afternoon"}, "quote": "In the afternoon ... about 45 minutes"}, [(T_MEET, "meetings")], (0.75, 0.5, 0.9)),
        act(5, "Product B work", "and then worked on Product B until 6", DEEP, {"kind": "range", "start_anchor": "previous_end", "end": tod(6), "quote": "and then ... until 6"}, [(T_B, "product-b")], (0.8, 0.7, 0.9)),
    ]}


def local(dt):
    return dt.astimezone(IST).strftime("%H:%M")


@pytest.mark.asyncio
async def test_prd_worked_example_end_to_end():
    res = await run_extraction(make_input(), FixtureProvider(prd_response()))
    d = {x.temp_id: x for x in res.drafts}
    assert [x.temp_id for x in res.drafts] == ["a1", "a2", "a3", "a4", "a5"]
    assert (local(d["a1"].start), local(d["a1"].end)) == ("09:30", "10:30") and d["a1"].certainty == "stated"
    assert (local(d["a2"].start), local(d["a2"].end), d["a2"].certainty) == ("10:30", "13:00", "inferred")
    assert (local(d["a3"].start), local(d["a3"].end)) == ("13:00", "14:00")
    assert d["a4"].placement == "unplaced" and d["a4"].duration == 45 and d["a4"].start is None
    assert d["a5"].placement == "unplaced" and "start_unknown" in d["a5"].flags
    assert all(x.source_quote and TEXT[x.source_start:x.source_end] == x.source_quote for x in res.drafts)  # offsets point at the exact words
    assert len(res.questions) == 1
    q = res.questions[0]
    assert q["type"] == "start_time" and q["activity_temp_id"] == "a4" and q["options"][0] == {"label": "Right after Lunch (2:00 pm)", "value": "14:00"}
    assert d["a4"].confidence <= 0.49 and d["a1"].confidence == 0.68  # unresolved question caps confidence
    assert {t.name for t in d["a2"].tags} == {"product-a", "bug"}


@pytest.mark.asyncio
async def test_ac020_a_quote_that_is_not_in_the_text_is_cleared_and_penalised():
    resp = prd_response()
    resp["activities"][2]["source_quote"] = "Ate a huge pizza with friends"  # invented
    res = await run_extraction(make_input(), FixtureProvider(resp))
    lunch = next(x for x in res.drafts if x.temp_id == "a3")
    assert lunch.source_quote is None and lunch.source_start is None and "quote_unverified" in lunch.flags
    assert lunch.confidence < 0.6  # min(0.95, 0.9, 0.95) x 0.60 x 0.9 meridiem


@pytest.mark.asyncio
async def test_invented_clock_times_are_dropped_and_never_placed():
    resp = prd_response()
    resp["activities"][2]["time_ref"] = {"kind": "range", "start": tod(7), "end": tod(8), "quote": "had lunch"}   # the quote contains neither 7 nor 8
    resp["activities"][2]["source_quote"] = "Had lunch from 1 to 2"
    res = await run_extraction(make_input(), FixtureProvider(resp))
    lunch = next(x for x in res.drafts if x.temp_id == "a3")
    assert lunch.placement == "unplaced" and lunch.start is None and "time_unsupported" in lunch.flags


@pytest.mark.asyncio
async def test_ac022_a_keyword_rule_tags_regardless_of_the_model():
    text = "Wasted half an hour scrolling Twitter on the sofa."
    resp = {"schema_version": "1", "entry_summary": "Twitter", "activities": [{
        "temp_id": "a1", "order": 1, "title": "Scrolling", "source_quote": "scrolling Twitter", "category_id": str(MEALS),
        "time_ref": {"kind": "duration", "duration_minutes": 30}, "tags": [], "confidence": {"overall": 0.9, "time": 0.9, "category": 0.9}}]}
    rules = [RuleInfo("twitter", "tag", T_SOCIAL)]
    res = await run_extraction(make_input(text, rules=rules), FixtureProvider(resp))
    t = res.drafts[0].tags[0]
    assert t.name == "social-media" and t.source == "rule" and t.reason == "twitter" and t.applied


def test_ac047_keyword_rules_match_whole_words_only():
    assert phrase_in("we went to a party", "party") and not phrase_in("we went to a party", "art")
    assert phrase_in("Twitter, mostly.", "twitter") and phrase_in("scrolled Instagram on the metro", "scrolled instagram")
    cands, _ = match_tags("great party tonight", [RuleInfo("art", "tag", T_A)], TAGS, [])
    assert cands == []


def test_ac049_archived_tags_are_never_candidates_and_merged_ones_resolve_to_the_target():
    old, target = uuid.uuid4(), uuid.uuid4()
    tags = [TagInfo(old, "prod-b", archived=True, merged_into_id=target), TagInfo(target, "product-b"), TagInfo(uuid.uuid4(), "retired", archived=True)]
    cands, _ = match_tags("x", [], tags, [{"tag_id": str(old), "name": "prod-b", "confidence": 0.9}, {"name": "retired", "confidence": 0.9}])
    assert [(c.name, c.tag_id) for c in cands] == [("product-b", target)]


def test_tag_confidence_below_half_is_not_applied_and_new_tags_are_suggested_once():
    cands, _ = match_tags("x", [], TAGS, [{"name": "bug", "tag_id": str(T_BUG), "confidence": 0.4}, {"name": "AI feature!", "new": True, "confidence": 0.9},
                                             {"name": "ai-feature", "new": True, "confidence": 0.8}])
    by = {c.name: c for c in cands}
    assert not by["bug"].applied and by["ai-feature"].new and by["ai-feature"].applied and len(cands) == 2
    alias_hit, _ = match_tags("x", [], TAGS, [{"name": "defect", "confidence": 0.9}])
    assert alias_hit[0].tag_id == T_BUG and alias_hit[0].source == "alias"


def test_quote_verifier_exact_loose_and_fuzzy():
    text = "Had lunch from 1 to 2.  Then, a long meeting."
    assert verify_quote(text, "Had lunch from 1 to 2").start == 0
    loose = verify_quote(text, "then a long   meeting")                # punctuation and case differ
    assert loose.verified and text[loose.start:loose.end].lower().startswith("then")
    assert verify_quote("I had a very long meeting about the roadmap today", "had a very long meeting about the roadmaps today").verified
    assert not verify_quote(text, "went skydiving over the alps").verified and not verify_quote(text, "").verified


def test_time_support_requires_the_hour_in_the_words():
    assert time_supported(9, "around 9:30") and time_supported(13, "until 1 PM") and time_supported(18, "until six") and time_supported(12, "at noon")
    assert not time_supported(7, "had lunch") and not time_supported(15, "from 1 to 2")


def test_task_matching_needs_similarity():
    t = OpenTask(uuid.uuid4(), "Fix sync bug")
    assert match_task({"task_id": str(t.id), "confidence": 0.9}, [t], "Fixing the sync bug", "").task_id == t.id            # AC-039
    assert match_task({"task_id": str(t.id), "confidence": 0.9}, [t], "Lunch", "").task_id is None                          # wrong link refused
    m = match_task({"new_task_title": "Write quarterly report", "confidence": 0.7}, [t], "Report", "")
    assert m.task_id is None and m.new_task_title == "Write quarterly report"
    assert match_task({"new_task_title": "the sync bug"}, [t], "x", "").task_id == t.id


@pytest.mark.asyncio
async def test_unknown_category_is_repaired_by_path_else_flagged_low_confidence():
    resp = prd_response()
    resp["activities"][0]["category_id"] = "Work › Deep work"            # a path instead of an id
    resp["activities"][2]["category_id"] = str(uuid.uuid4())             # unknown id
    res = await run_extraction(make_input(), FixtureProvider(resp))
    d = {x.temp_id: x for x in res.drafts}
    assert d["a1"].category_id == DEEP and "category_unresolved" not in d["a1"].flags
    assert d["a3"].category_id == WORK_ROOT and "category_unresolved" in d["a3"].flags and d["a3"].confidence <= 0.3


@pytest.mark.asyncio
async def test_invalid_output_gets_one_repair_call_then_fails():
    bad = {"schema_version": "1", "activities": [{"temp_id": "a1"}]}   # missing required fields
    ok = await run_extraction(make_input(), FixtureProvider([bad, prd_response()]))
    assert len(ok.drafts) == 5
    prov = FixtureProvider([bad, bad])
    with pytest.raises(ExtractionFailed) as e:
        await run_extraction(make_input(), prov)
    assert e.value.code == "INVALID_MODEL_OUTPUT" and len(prov.requests) == 2
    assert "did not match the schema" in prov.requests[1].user                        # the repair call carries the validation errors


@pytest.mark.asyncio
async def test_duplicates_of_confirmed_activities_are_unchecked_and_linked():
    existing = [Existing(uuid.uuid4(), "Lunch", "placed", parse_local(DAY, time(13), IST), parse_local(DAY, time(14), IST), DAY, MEALS, "Had lunch from 1 to 2")]
    res = await run_extraction(make_input(existing=existing), FixtureProvider(prd_response()))
    lunch = next(x for x in res.drafts if x.temp_id == "a3")
    assert lunch.include is False and lunch.duplicate_of == existing[0].id and "possible_duplicate" in lunch.flags
    assert all(x.include for x in res.drafts if x.temp_id != "a3")


@pytest.mark.asyncio
async def test_empty_entries_return_no_activities_not_an_error():
    res = await run_extraction(make_input("Felt tired and a bit anxious today."), FixtureProvider({"schema_version": "1", "entry_summary": "", "activities": [], "warnings": ["No activities"]}))
    assert res.drafts == [] and res.questions == [] and res.warnings == ["No activities"]


def test_ac027_the_model_payload_holds_the_entry_and_taxonomy_but_no_identity():
    inp = make_input()
    ctx = build_context(text="I met Priya Sharma (priya@example.com is not mine) for coffee", window_start=inp.window_start, window_end=inp.window_end, now=inp.now, tz=IST,
                        tz_name="Asia/Kolkata", categories=CATS, tags=TAGS, rules=[], tasks=[], hint="focus on work")
    payload = ctx.system + ctx.user
    for forbidden in ("bhavan", "demo.cadence", "user_id", "access_token", "password"):
        assert forbidden not in payload.lower()
    assert "<journal_entry>" in ctx.user and "Work › Deep work" in ctx.user and "focus on work" in ctx.user and "id=" + str(T_BUG) in ctx.user
    assert "Entry window (local time, Asia/Kolkata): Fri 13 Nov 2026, 09:00 to Fri 13 Nov 2026, 18:00" in ctx.user


@pytest.mark.asyncio
async def test_the_offline_provider_produces_a_usable_extraction_from_the_prd_text():
    res = await run_extraction(make_input(), FakeProvider())
    assert len(res.drafts) >= 4
    placed = [x for x in res.drafts if x.placement == "placed"]
    assert any(local(x.end) == "13:00" for x in placed)                                # "until 1 PM"
    lunch = next(x for x in res.drafts if "lunch" in x.title.lower())
    assert (local(lunch.start), local(lunch.end)) == ("13:00", "14:00") and lunch.category_id == MEALS
    meet = next(x for x in res.drafts if "meeting" in x.title.lower())
    assert meet.placement == "unplaced" and meet.duration == 45                         # "In the afternoon ... 45 minutes"
    assert all(x.source_quote and x.source_quote in TEXT for x in res.drafts)           # verbatim quotes
