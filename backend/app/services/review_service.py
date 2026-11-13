"""Review and commit (FR-043..FR-051, FR-048): drafts live in `activities` as status=draft and are invisible to analytics
until a single transaction confirms them."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import clarifications as clar
from app.ai import confidence as conf
from app.ai import detectors
from app.ai.extraction_pipeline import PipelineResult, question_specs, to_item
from app.ai.tag_matcher import normalise_tag_name
from app.ai.time_resolver import resolve_day
from app.core.database import rolls_back_on_error
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.time import ensure_utc, floor_minute, get_zone, local_date_of
from app.models import Activity, ActivityTag, AIProcessingJob, Category, JournalEntry, Tag, Task, User
from app.models.enums import (
    ActivityEventType,
    ActivityKind,
    ActivityOrigin,
    ActivityStatus,
    AiJobStatus,
    EntryStatus,
    EventActor,
    Placement,
    TagSource,
    TimeCertainty,
)
from app.repositories.activities import ActivitiesRepository
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.journal import JobBrief
from app.schemas.review import CommitIn, ReviewOut
from app.services import serializers, slice_service
from app.services.category_service import PALETTE
from app.services.ideal_service import IdealService
from app.services.tag_service import auto_color

SOURCE_MAP = {"rule": TagSource.rule, "alias": TagSource.alias, "ai": TagSource.ai}


def _tz(entry: JournalEntry) -> ZoneInfo:
    return get_zone(entry.timezone)


# ======================================================================================================================
# persistence of a pipeline result (called by the worker)
# ======================================================================================================================
async def persist_result(session: AsyncSession, user: User, entry: JournalEntry, job: AIProcessingJob, result: PipelineResult) -> None:
    tz = _tz(entry)
    # Older drafts of this entry belong to a previous run; they are replaced, never mixed in.
    await session.execute(delete(Activity).where(Activity.user_id == user.id, Activity.journal_entry_id == entry.id, Activity.status == ActivityStatus.draft))
    for d in result.drafts:
        anchor = d.start or d.window_start
        a = Activity(
            user_id=user.id, journal_entry_id=entry.id, source_job_id=job.id, status=ActivityStatus.draft, kind=ActivityKind.actual, title=d.title,
            description=d.description, category_id=d.category_id, location_type=d.location_type, placement=Placement(d.placement), start_at=d.start,
            end_at=d.end, window_start_at=d.window_start, window_end_at=d.window_end, duration_minutes=d.duration, time_certainty=TimeCertainty(d.certainty),
            timezone=entry.timezone, local_date=local_date_of(anchor, tz) if anchor else entry.entry_date, origin=ActivityOrigin.ai, confidence=d.confidence,
            needs_review=conf.band(d.confidence) != "high", flags=d.flags, source_quote=d.source_quote, source_start=d.source_start, source_end=d.source_end,
            source_revision=job.entry_revision, ai_proposed=d.proposed())
        session.add(a)
        await session.flush()
        for t in d.tags:
            if t.tag_id and t.applied:
                session.add(ActivityTag(activity_id=a.id, tag_id=t.tag_id, user_id=user.id, source=SOURCE_MAP.get(t.source, TagSource.ai),
                                        confidence=round(t.confidence, 2), reason=(t.reason or "")[:160] or None))
    job.parsed_response = {"summary": result.summary, "questions": result.questions, "answers": {}, "warnings": result.warnings, "rejected": [], "model_output": result.parsed}
    job.raw_response = result.llm.raw
    job.input_tokens, job.output_tokens, job.latency_ms = result.llm.input_tokens, result.llm.output_tokens, result.llm.latency_ms
    if not entry.title and result.summary:
        entry.title = result.summary[:120]
    await session.flush()


# ======================================================================================================================
class ReviewService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.tax = TaxonomyRepository(session, user.id)
        self.acts = ActivitiesRepository(session, user.id)

    # ------------------------------------------------------------------ loading
    async def _entry(self, entry_id: uuid.UUID, *, for_update: bool = False) -> JournalEntry:
        e = await self.tax.get(JournalEntry, entry_id, for_update=for_update)
        if e is None:
            raise NotFound("Entry not found")
        return e

    async def _job(self, entry: JournalEntry, job_id: uuid.UUID | None, *, ready: bool = True) -> AIProcessingJob:
        jid = job_id or entry.latest_job_id
        job = await self.session.get(AIProcessingJob, jid) if jid else None
        if job is None or job.user_id != self.user.id or job.entry_id != entry.id:
            raise NotFound("Job not found")
        if ready and job.status != AiJobStatus.succeeded:
            raise Conflict("The AI is still working on this entry", code="JOB_NOT_READY", details={"status": job.status.value})
        return job

    async def _drafts(self, entry: JournalEntry, job: AIProcessingJob) -> list[Activity]:
        rows = (await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.journal_entry_id == entry.id, Activity.source_job_id == job.id,
            Activity.status == ActivityStatus.draft, Activity.deleted_at.is_(None)))).scalars().all()
        return sorted(rows, key=lambda a: (a.ai_proposed or {}).get("order", 0))

    async def _existing_confirmed(self, entry: JournalEntry) -> list[Activity]:
        lo, hi = entry.covers_start_at - timedelta(hours=12), entry.covers_end_at + timedelta(hours=12)
        return list((await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual, Activity.deleted_at.is_(None),
            Activity.placement == Placement.placed, Activity.start_at < hi, Activity.end_at > lo).order_by(Activity.start_at))).scalars())

    # ------------------------------------------------------------------ E-30
    async def payload(self, entry_id: uuid.UUID, job_id: uuid.UUID | None = None) -> ReviewOut:
        entry = await self._entry(entry_id)
        job = await self._job(entry, job_id)
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        drafts = await self._drafts(entry, job)
        existing = await self._existing_confirmed(entry)
        parsed = job.parsed_response or {}
        questions = parsed.get("questions", [])

        cats = {c.id: c for c in await self.tax.categories(include_archived=True)}
        tags = {t.id: t for t in await self.tax.tags(include_archived=True)}
        ideal = await self._ideal(entry, cats)
        owner_of = ideal["owner_of"] if ideal else (lambda _cid: None)

        existing_by_id = {e.id: e for e in existing}
        extra_dup = {}
        for d in drafts:
            dup = (d.ai_proposed or {}).get("duplicate_of")
            if dup and uuid.UUID(dup) not in existing_by_id:
                a = await self.session.get(Activity, uuid.UUID(dup))
                if a is not None:
                    extra_dup[a.id] = a

        out_drafts, included = [], []
        for d in drafts:
            p = d.ai_proposed or {}
            cat = cats[d.category_id]
            tlist = []
            for t in p.get("tags", []):
                tid = uuid.UUID(t["tag_id"]) if t.get("tag_id") else None
                tag = tags.get(tid) if tid else None
                tlist.append({"tag_id": tid, "name": t["name"], "color": tag.color if tag else auto_color(t["name"]), "source": t["source"], "confidence": t["confidence"],
                              "reason": t.get("reason"), "applied": bool(t["applied"]), "new": bool(t["new"])})
            tk = p.get("task") or {}
            dup_id = p.get("duplicate_of")
            dup_obj = existing_by_id.get(uuid.UUID(dup_id)) if dup_id else None
            dup_obj = dup_obj or (extra_dup.get(uuid.UUID(dup_id)) if dup_id else None)
            conf_v = float(d.confidence or 0)
            row = {
                "id": d.id, "temp_id": p.get("temp_id", ""), "order": p.get("order", 0), "title": d.title, "description": d.description, "placement": d.placement.value,
                "start_at": d.start_at, "end_at": d.end_at, "window_start_at": d.window_start_at, "window_end_at": d.window_end_at, "duration_minutes": d.duration_minutes,
                "time_certainty": d.time_certainty.value, "category": {"id": cat.id, "name": cat.name, "path_names": cat.path_names, "color": cat.color, "root_kind": cat.root_kind.value},
                "tags": tlist, "task": {"task_id": tk.get("task_id"), "task_title": tk.get("task_title"), "new_task_title": tk.get("new_task_title"), "confidence": tk.get("confidence", 0)},
                "location_type": d.location_type, "confidence": conf_v, "band": conf.band(conf_v), "flags": list(d.flags or []),
                "source": {"quote": d.source_quote, "start": d.source_start, "end": d.source_end}, "include": bool(p.get("include", True)),
                "duplicate_of": {"id": dup_obj.id, "title": dup_obj.title, "start_at": dup_obj.start_at} if dup_obj else None, "ideal_row_id": owner_of(d.category_id)}
            out_drafts.append(row)
            if row["include"]:
                included.append(d)

        w0, w1 = entry.covers_start_at, entry.covers_end_at
        placed_inc = [detectors.Span(str(d.id), d.start_at, d.end_at, d.title) for d in included if d.placement == Placement.placed]
        ex_spans = [detectors.Span(str(e.id), e.start_at, e.end_at, e.title) for e in existing]
        gap_list = detectors.gaps([(s.start, s.end) for s in placed_inc + ex_spans if s.end > w0 and s.start < w1], w0, w1, prefs.gap_min_minutes)
        conflicts = [{"draft_id": uuid.UUID(c.draft_id), "other_id": uuid.UUID(c.other_id), "other_title": c.other_title, "other_is_draft": c.other_is_draft,
                      "start_at": c.start, "end_at": c.end, "overlap_minutes": c.overlap_minutes} for c in detectors.overlaps(placed_inc, ex_spans)]

        asked = {q["activity_temp_id"] for q in questions}
        blocking = []
        for d in included:
            tid = (d.ai_proposed or {}).get("temp_id")
            if d.duration_minutes is None:
                blocking.append({"draft_id": d.id, "reason": "MISSING_DURATION"})
            elif tid in asked:
                blocking.append({"draft_id": d.id, "reason": "UNANSWERED_QUESTION"})
        blocking += [{"draft_id": c["draft_id"], "reason": "OVERLAP"} for c in conflicts]

        summary = {"activity_count": len(included), "covered_minutes": sum(d.duration_minutes or 0 for d in included), "not_mentioned_minutes": sum(detectors.minutes(a, b) for a, b in gap_list),
                   "gap_count": len(gap_list), "to_double_check": sum(1 for r in out_drafts if r["include"] and r["band"] != "high"),
                   "tags_applied": sum(1 for r in out_drafts if r["include"] for t in r["tags"] if t["applied"])}
        previous = (await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.journal_entry_id == entry.id, Activity.origin == ActivityOrigin.ai, Activity.status == ActivityStatus.confirmed,
            Activity.deleted_at.is_(None)))).scalars().all()
        return ReviewOut.model_validate({
            "entry": {"id": entry.id, "status": entry.status.value, "title": entry.title, "raw_text": entry.raw_text, "covers_start_at": entry.covers_start_at,
                      "covers_end_at": entry.covers_end_at, "timezone": entry.timezone, "revision": entry.revision, "input_method": entry.input_method.value,
                      "dictation_seconds": entry.dictation_seconds},
            "job": JobBrief(id=job.id, status=job.status.value, error_code=job.error_code, is_stale=job.is_stale, provider=job.provider, model=job.model),
            "summary": summary, "drafts": out_drafts,
            "gaps": [{"start_at": a, "end_at": b, "minutes": detectors.minutes(a, b)} for a, b in gap_list], "conflicts": conflicts, "questions": questions,
            "blocking": blocking, "warnings": parsed.get("warnings", []), "ideal": ideal["preview"] if ideal else None,
            "replace_candidates": [{"id": a.id, "title": a.title, "user_edited": a.user_edited} for a in previous]})

    async def _ideal(self, entry: JournalEntry, cats: dict) -> dict | None:
        day = local_date_of(entry.covers_start_at, _tz(entry))
        prog = await IdealService(self.session, self.user).progress("day", day)
        if not prog.rows:
            return None
        ids = {r.category_id for r in prog.rows}

        def owner_of(cid: uuid.UUID):
            c = cats.get(cid)
            return next((x for x in (c.path_ids if c else []) if x in ids), None)

        return {"owner_of": owner_of, "preview": {"date": day, "other_actual": prog.other_actual,
                "rows": [{"category_id": r.category_id, "name": r.name, "color": r.color, "target": r.target, "actual": r.actual} for r in prog.rows]}}

    # ------------------------------------------------------------------ E-31
    @rolls_back_on_error
    async def answer(self, entry_id: uuid.UUID, job_id: uuid.UUID, question_id: str, value: str) -> ReviewOut:
        entry = await self._entry(entry_id)
        job = await self._job(entry, job_id)
        parsed = dict(job.parsed_response or {})
        q = next((x for x in parsed.get("questions", []) if x["id"] == question_id), None)
        if q is None:
            raise AppError("That question is not open", code="INVALID_ANSWER", status=422)
        try:
            answers = clar.apply_answer(parsed.get("answers", {}), q, value)
        except (ValueError, KeyError, IndexError) as e:
            raise AppError("That answer is not valid for this question", code="INVALID_ANSWER", status=422) from e
        drafts = await self._drafts(entry, job)
        titles = {(d.ai_proposed or {})["temp_id"]: d.title for d in drafts}
        items = [to_item(d.ai_proposed["temp_id"], d.ai_proposed["time_ref"], answers) for d in drafts]
        resolved = resolve_day(items, entry.covers_start_at, entry.covers_end_at, _tz(entry))
        for d, r in zip(drafts, resolved, strict=True):
            p = d.ai_proposed
            d.placement, d.start_at, d.end_at, d.duration_minutes = Placement(r.placement), r.start, r.end, r.duration
            d.window_start_at, d.window_end_at = (None, None) if r.placement == "placed" else (r.window_start, r.window_end)
            d.time_certainty = TimeCertainty(r.certainty)
            flags = sorted(set(p.get("base_flags", [])) | set(r.flags))
            lc = p["llm_conf"]
            d.flags = flags
            d.confidence = conf.final_confidence(lc["overall"], lc["time"], lc.get("category", 0.8), set(flags), unresolved=bool(r.blockers))
            d.needs_review = conf.band(float(d.confidence)) != "high"
            anchor = d.start_at or d.window_start_at
            if anchor:
                d.local_date = local_date_of(anchor, _tz(entry))
        parsed["answers"] = answers
        parsed["questions"] = clar.build_questions(question_specs(items, resolved, titles), _tz(entry))
        job.parsed_response = parsed
        await self.session.commit()
        return await self.payload(entry_id, job_id)

    # ------------------------------------------------------------------ E-32
    @rolls_back_on_error
    async def commit(self, entry_id: uuid.UUID, body: CommitIn) -> dict:
        entry = await self._entry(entry_id, for_update=True)
        job = await self._job(entry, body.job_id)
        if entry.latest_job_id != job.id:
            raise Conflict("A newer run exists for this entry", code="JOB_NOT_LATEST")
        if entry.status not in (EntryStatus.review, EntryStatus.confirmed):
            raise Conflict("This entry is not waiting for review", code="ENTRY_NOT_IN_REVIEW")
        tz = _tz(entry)
        drafts = await self._drafts(entry, job)
        by_id = {d.id: d for d in drafts}
        unknown = [str(c.draft_id) for c in body.activities if c.draft_id not in by_id]
        if unknown:
            raise ValidationFailed("Unknown draft", path="activities", rule="not_found", details={"draft_ids": unknown})
        picks = {c.draft_id: c for c in body.activities}
        parsed = dict(job.parsed_response or {})

        # ---------------------------------------------------------------- plan finals
        finals: dict[uuid.UUID, dict] = {}
        for d in drafts:
            pick = picks.get(d.id)
            include = pick.include if pick else bool((d.ai_proposed or {}).get("include", True))
            if not include:
                continue
            ed = pick.edits if pick and pick.edits else None
            f = {"title": d.title, "description": d.description, "category_id": d.category_id, "placement": d.placement, "start": d.start_at, "end": d.end_at,
                 "w0": d.window_start_at, "w1": d.window_end_at, "duration": d.duration_minutes, "location": d.location_type, "edited": False, "tag_ids": None,
                 "task_id": None, "new_task_title": None, "edits": ed}
            if ed:
                if ed.title is not None:
                    f["title"], f["edited"] = ed.title, f["edited"] or ed.title != d.title
                if "description" in ed.model_fields_set and ed.description is not None:
                    f["description"], f["edited"] = ed.description, True
                if ed.category_id:
                    cat = await self.tax.category(ed.category_id)
                    if cat is None or cat.archived_at is not None:
                        raise ValidationFailed("Unknown or archived category", path="activities.category_id", rule="not_found")
                    f["category_id"], f["edited"] = cat.id, f["edited"] or cat.id != d.category_id
                if ed.location_type:
                    f["location"], f["edited"] = ed.location_type, True
                if ed.start_at and ed.end_at:
                    s, e = floor_minute(ensure_utc(ed.start_at, tz)), floor_minute(ensure_utc(ed.end_at, tz))
                    if e <= s or e - s > timedelta(hours=24):
                        raise ValidationFailed("Invalid time range", path="activities.end_at", rule="invalid_range")
                    f.update(placement=Placement.placed, start=s, end=e, w0=None, w1=None, duration=int((e - s).total_seconds() // 60), edited=True)
                elif ed.duration_minutes or ed.window_start_at or ed.window_end_at:
                    w0 = floor_minute(ensure_utc(ed.window_start_at, tz)) if ed.window_start_at else (d.window_start_at or d.start_at)
                    w1 = floor_minute(ensure_utc(ed.window_end_at, tz)) if ed.window_end_at else (d.window_end_at or d.end_at)
                    f.update(placement=Placement.unplaced, start=None, end=None, w0=w0, w1=w1, duration=ed.duration_minutes or d.duration_minutes, edited=True)
                if ed.tag_ids is not None:
                    f["tag_ids"], f["edited"] = list(dict.fromkeys(ed.tag_ids)), True
                f["task_id"], f["new_task_title"] = ed.task_id, ed.new_task_title
            finals[d.id] = f

        blockers: list[dict] = []
        for did, f in finals.items():
            if f["duration"] is None or not (1 <= f["duration"] <= 1440):
                blockers.append({"draft_id": str(did), "reason": "MISSING_DURATION"})
            if f["placement"] == Placement.unplaced and (f["w0"] is None or f["w1"] is None or f["w1"] <= f["w0"]):
                blockers.append({"draft_id": str(did), "reason": "MISSING_DURATION"})
        if blockers:
            raise Conflict(f"{len(blockers)} items need attention", code="REVIEW_BLOCKED", details={"blockers": blockers})

        # ---------------------------------------------------------------- previous AI activities of this entry
        replaced: list[Activity] = []
        kept_edited: list[uuid.UUID] = []
        if body.replace_previous:
            earlier = (await self.session.execute(select(Activity).where(
                Activity.user_id == self.user.id, Activity.journal_entry_id == entry.id, Activity.origin == ActivityOrigin.ai, Activity.status == ActivityStatus.confirmed,
                Activity.deleted_at.is_(None), Activity.source_job_id != job.id))).scalars().all()
            for a in earlier:
                (kept_edited.append(a.id) if a.user_edited else replaced.append(a))

        # ---------------------------------------------------------------- overlaps against what exists (after replacement and resolutions)
        replaced_ids = {a.id for a in replaced}
        existing = [e for e in await self._existing_confirmed_range(finals) if e.id not in replaced_ids]
        resolutions: dict[uuid.UUID, list] = {}
        for r in body.conflict_resolutions:
            resolutions.setdefault(r.draft_id, []).append(r)
        to_delete: set[uuid.UUID] = set()
        trims: dict[uuid.UUID, tuple[datetime, datetime]] = {}
        for did, f in finals.items():
            if f["placement"] != Placement.placed:
                continue
            for r in resolutions.get(did, []):
                def cur(e):
                    return trims.get(e.id, (e.start_at, e.end_at))  # an activity already trimmed for an earlier row keeps its new bounds

                clash = [e for e in existing if e.id not in to_delete and cur(e)[0] < f["end"] and f["start"] < cur(e)[1] and (r.existing_id in (None, e.id))]
                for e in clash:
                    cs, ce = cur(e)
                    if r.action == "replace_existing":
                        to_delete.add(e.id)
                    elif r.action == "trim_existing":
                        if cs < f["start"]:
                            new = (cs, min(ce, f["start"]))
                        elif ce > f["end"]:
                            new = (max(cs, f["end"]), ce)
                        else:
                            new = None  # the new row sits inside it: trimming cannot make room
                        if new and (new[1] - new[0]) >= timedelta(minutes=1):
                            trims[e.id] = new
                    elif r.action == "trim_new":
                        if f["start"] < ce <= f["end"] and cs <= f["start"]:
                            f["start"] = ce
                        elif f["start"] <= cs < f["end"] and ce >= f["end"]:
                            f["end"] = cs
                        f["duration"] = int((f["end"] - f["start"]).total_seconds() // 60)
                        f["edited"] = True
                    elif r.action == "keep_unplaced":
                        f.update(placement=Placement.unplaced, w0=f["start"], w1=f["end"], start=None, end=None, edited=True)
                        break
        spans_existing = []
        for e in existing:
            if e.id in to_delete:
                continue
            s, en = trims.get(e.id, (e.start_at, e.end_at))
            spans_existing.append(detectors.Span(str(e.id), s, en, e.title))
        placed_finals = [detectors.Span(str(did), f["start"], f["end"], f["title"]) for did, f in finals.items() if f["placement"] == Placement.placed and f["duration"] and f["duration"] >= 1]
        for c in detectors.overlaps(placed_finals, spans_existing):
            blockers.append({"draft_id": c.draft_id, "reason": "OVERLAP", "other_id": c.other_id, "other_title": c.other_title, "overlap_minutes": c.overlap_minutes})
        if blockers:
            raise Conflict(f"{len(blockers)} items need attention", code="REVIEW_BLOCKED", details={"blockers": blockers})

        transition_cat = None
        if body.transitions:
            transition_cat = next((c for c in await self.tax.categories() if c.is_transition), None)
            if transition_cat is None:
                raise AppError("Create a category marked as a transition first", code="NO_TRANSITION_CATEGORY", status=422)

        # ---------------------------------------------------------------- write (still one transaction)
        svc_acts = ActivitiesRepository(self.session, self.user.id)
        from app.services.activity_service import ActivityService

        act_service = ActivityService(self.session, self.user)
        for a in replaced:
            await act_service._soft_delete(a)
        for e in existing:
            if e.id in to_delete:
                await act_service._soft_delete(e)
            elif e.id in trims:
                e.start_at, e.end_at = trims[e.id]
                e.duration_minutes = int((e.end_at - e.start_at).total_seconds() // 60)
                e.user_edited, e.version = True, e.version + 1
                await self.session.flush()
                svc_acts.add_event(e.id, ActivityEventType.edited, EventActor.user, {"changes": {"end_at": ["trimmed for a journal entry"]}})
                await slice_service.rebuild(self.session, e)

        tag_by_name = {t.name: t for t in await self.tax.tags(include_archived=True)}
        created_tags, created_tasks = [], []
        keep_tags: dict[uuid.UUID, set[str]] = {}
        for nt in body.new_tags:
            if nt.keep:
                keep_tags.setdefault(nt.draft_id, set()).add(nt.name)
        confirmed: list[Activity] = []
        rejected = list(parsed.get("rejected", []))
        for d in drafts:
            if d.id not in finals:
                p = d.ai_proposed or {}
                rejected.append({"temp_id": p.get("temp_id"), "title": d.title, "source_quote": d.source_quote, "proposed": p})
                await self.session.delete(d)
                continue
            f, p = finals[d.id], d.ai_proposed or {}
            d.title, d.description, d.category_id, d.location_type = f["title"], f["description"], f["category_id"], f["location"]
            d.placement, d.start_at, d.end_at, d.window_start_at, d.window_end_at, d.duration_minutes = f["placement"], f["start"], f["end"], f["w0"], f["w1"], f["duration"]
            anchor = d.start_at or d.window_start_at
            d.local_date = local_date_of(anchor, tz) if anchor else entry.entry_date
            d.status, d.kind, d.origin, d.needs_review, d.user_edited = ActivityStatus.confirmed, ActivityKind.actual, ActivityOrigin.ai, False, f["edited"]
            if f["edited"] and d.time_certainty == TimeCertainty.inferred and f["edits"] and (f["edits"].start_at or f["edits"].duration_minutes):
                d.time_certainty = TimeCertainty.stated  # the person typed it
            # tags: the person's final list wins; otherwise the applied proposals
            await self.session.execute(delete(ActivityTag).where(ActivityTag.activity_id == d.id))
            cand_by_id = {t["tag_id"]: t for t in p.get("tags", []) if t.get("tag_id")}
            wanted: dict[uuid.UUID, tuple[TagSource, float | None, str | None]] = {}
            if f["tag_ids"] is not None:
                for tid in f["tag_ids"]:
                    tag = await self.tax.tag(tid)
                    if tag is None or tag.archived_at is not None:
                        raise ValidationFailed("Unknown or archived tag", path="activities.tag_ids", rule="not_found")
                    c = cand_by_id.get(str(tid))
                    wanted[tid] = (SOURCE_MAP.get(c["source"], TagSource.ai), c["confidence"], c.get("reason")) if c else (TagSource.user, None, None)
            else:
                for c in p.get("tags", []):
                    if c.get("tag_id") and c["applied"]:
                        wanted[uuid.UUID(c["tag_id"])] = (SOURCE_MAP.get(c["source"], TagSource.ai), c["confidence"], c.get("reason"))
            for name in sorted(keep_tags.get(d.id, set())):
                norm = normalise_tag_name(name)
                if not norm:
                    raise ValidationFailed("Invalid tag name", path="new_tags.name", rule="invalid")
                tag = tag_by_name.get(norm)
                if tag is None:
                    tag = Tag(user_id=self.user.id, name=norm, color=auto_color(norm))
                    self.session.add(tag)
                    await self.session.flush()
                    tag_by_name[norm] = tag
                    created_tags.append(norm)
                wanted.setdefault(tag.id, (TagSource.ai, 0.8, "suggested by AI, kept by you"))
            for tid, (src, cf, reason) in wanted.items():
                self.session.add(ActivityTag(activity_id=d.id, tag_id=tid, user_id=self.user.id, source=src, confidence=cf, reason=(reason or "")[:160] or None))
            # task
            tk = p.get("task") or {}
            ed = f["edits"]
            if ed and ed.clear_task:
                d.task_id = None
            elif f["task_id"]:
                task = await self.tax.get(Task, f["task_id"])
                if task is None:
                    raise ValidationFailed("Unknown task", path="activities.task_id", rule="not_found")
                d.task_id, d.project_id = task.id, task.project_id
            elif f["new_task_title"]:
                task = Task(user_id=self.user.id, title=f["new_task_title"][:160])
                self.session.add(task)
                await self.session.flush()
                d.task_id = task.id
                created_tasks.append(task.title)
            elif tk.get("task_id"):
                task = await self.tax.get(Task, uuid.UUID(tk["task_id"]))
                if task is not None:
                    d.task_id, d.project_id = task.id, task.project_id
            d.version += 1
            confirmed.append(d)

        for t in body.transitions:
            s, e = floor_minute(ensure_utc(t.start_at, tz)), floor_minute(ensure_utc(t.end_at, tz))
            if e <= s:
                raise ValidationFailed("Invalid transition", path="transitions", rule="invalid_range")
            tr = Activity(user_id=self.user.id, journal_entry_id=entry.id, title="Transition", category_id=transition_cat.id, placement=Placement.placed, start_at=s, end_at=e,  # type: ignore[union-attr]
                          duration_minutes=int((e - s).total_seconds() // 60), timezone=entry.timezone, local_date=local_date_of(s, tz), origin=ActivityOrigin.manual,
                          status=ActivityStatus.confirmed)
            self.session.add(tr)
            confirmed.append(tr)
            await self.session.flush()
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            if "activities_no_overlap" in str(e.orig):
                raise Conflict("Some activities overlap", code="REVIEW_BLOCKED", details={"blockers": [{"reason": "OVERLAP"}]}) from e
            raise
        for a in confirmed:
            svc_acts.add_event(a.id, ActivityEventType.created, EventActor.ai if a.origin == ActivityOrigin.ai else EventActor.user, {"origin": a.origin.value, "job_id": str(job.id)})
            svc_acts.add_event(a.id, ActivityEventType.approved, EventActor.user, {"edited": a.user_edited})
            await slice_service.rebuild(self.session, a)
        entry.status = EntryStatus.confirmed
        parsed["rejected"], parsed["committed_at"] = rejected, datetime.now(UTC).isoformat()
        job.parsed_response = parsed
        await UsersRepository(self.session).bump_revision(self.user.id)
        await self.session.commit()
        for a in confirmed:
            await self.session.refresh(a)
        return {"activities": await serializers.activities_out(self.session, self.user.id, confirmed), "created_tags": created_tags, "created_tasks": created_tasks,
                "replaced": [a.id for a in replaced], "kept_edited": kept_edited}

    async def _existing_confirmed_range(self, finals: dict[uuid.UUID, dict]) -> list[Activity]:
        placed = [f for f in finals.values() if f["placement"] == Placement.placed and f["start"] and f["end"]]
        if not placed:
            return []
        lo, hi = min(f["start"] for f in placed), max(f["end"] for f in placed)
        return list((await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual, Activity.deleted_at.is_(None),
            Activity.placement == Placement.placed, Activity.start_at < hi, Activity.end_at > lo).with_for_update())).scalars())


__all__ = ["ReviewService", "persist_result", "PALETTE", "Category"]
