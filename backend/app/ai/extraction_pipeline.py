"""Orchestrates PRD 4.6: the LLM reads language (step D); every other step is deterministic code.
Pure with respect to the database: callers pass plain data in and persist the result."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from rapidfuzz import fuzz, process

from app.ai import clarifications as clar
from app.ai import confidence as conf
from app.ai import detectors
from app.ai.context_builder import CategoryInfo, build_context
from app.ai.output_models import ExtractedActivity, ExtractionOutput, TimeOfDay
from app.ai.providers.base import ProviderOutputError, StructuredRequest, StructuredResponse
from app.ai.quote_verifier import time_supported, verify_quote
from app.ai.tag_matcher import RuleInfo, TagCandidate, TagInfo, match_tags
from app.ai.task_matcher import OpenTask, TaskMatch, match_task
from app.ai.time_resolver import ItemIn, ItemOut, Spoken, resolve_day

MAX_ACTIVITIES = 40


class ExtractionFailed(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Existing:
    """A confirmed activity the draft might overlap or duplicate."""
    id: uuid.UUID
    title: str
    placement: str
    start: datetime | None
    end: datetime | None
    local_date: Any
    category_id: uuid.UUID
    source_quote: str | None = None


@dataclass
class PipelineInput:
    text: str
    window_start: datetime
    window_end: datetime
    tz: ZoneInfo
    tz_name: str
    now: datetime
    categories: list[CategoryInfo]
    tags: list[TagInfo]
    rules: list[RuleInfo]
    open_tasks: list[OpenTask]
    existing: list[Existing] = field(default_factory=list)
    gap_min_minutes: int = 10
    hint: str | None = None


@dataclass
class DraftSpec:
    temp_id: str
    order: int
    title: str
    description: str | None
    category_id: uuid.UUID
    placement: str
    start: datetime | None
    end: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    duration: int | None
    certainty: str
    location_type: str | None
    confidence: float
    flags: list[str]
    source_quote: str | None
    source_start: int | None
    source_end: int | None
    tags: list[TagCandidate]
    task: TaskMatch
    time_ref: dict
    llm_conf: dict
    include: bool = True
    duplicate_of: uuid.UUID | None = None
    base_flags: list[str] = field(default_factory=list)

    def proposed(self) -> dict:
        """The first-proposal snapshot kept on the activity (`ai_proposed`) and the input for re-resolution."""
        return {"temp_id": self.temp_id, "order": self.order, "title": self.title, "description": self.description,
                "category_id": str(self.category_id), "time_ref": self.time_ref, "llm_conf": self.llm_conf,
                "tags": [t.as_dict() for t in self.tags], "task": self.task.as_dict(), "include": self.include,
                "duplicate_of": str(self.duplicate_of) if self.duplicate_of else None, "location_type": self.location_type, "base_flags": self.base_flags,
                "start": self.start.isoformat() if self.start else None, "end": self.end.isoformat() if self.end else None,
                "duration": self.duration}


@dataclass
class PipelineResult:
    summary: str
    drafts: list[DraftSpec]
    questions: list[dict]
    warnings: list[str]
    llm: StructuredResponse
    parsed: dict
    rejected: list[dict] = field(default_factory=list)


# ------------------------------------------------------------------------------------------------------------------
def _spoken(t: TimeOfDay | None) -> Spoken | None:
    return Spoken(t.hour, t.minute, t.meridiem) if t else None


def to_item(key: str, ref: dict, answers: dict | None = None) -> ItemIn:
    """Rebuild a resolver input from a stored `time_ref` dict (used on first run and on every answered question)."""
    def sp(d):
        return Spoken(d["hour"], d.get("minute", 0), d.get("meridiem")) if d else None
    return ItemIn(key=key, kind=ref.get("kind", "none"), start=sp(ref.get("start")), end=sp(ref.get("end")), start_anchor=ref.get("start_anchor"),
                  end_anchor=ref.get("end_anchor"), duration=ref.get("duration_minutes"), approximate=bool(ref.get("approximate")),
                  window_label=(ref.get("window") or {}).get("label"), day_offset=ref.get("day_offset", 0), answers=(answers or {}).get(key, {}))


def question_specs(items: list[ItemIn], resolved: list[ItemOut], titles: dict[str, str]) -> list[clar.QuestionSpec]:
    specs, prev_title, prev_end, prev_blocked = [], None, None, False
    for i, (it, r) in enumerate(zip(items, resolved, strict=True)):
        # An activity that only waits on a previous one that is itself still blocked does not ask its own question;
        # once that neighbour is settled (answered, or kept as "some time"), it asks for itself.
        waits_on_previous = it.start_anchor == "previous_end" and "start_unknown" in r.flags and "start_time" in r.blockers and prev_blocked
        for b in r.blockers:
            if b == "start_time" and waits_on_previous:
                continue
            later = sum(1 for x in resolved[i + 1:] if "start_unknown" in x.flags)
            ambiguous = None
            if b == "meridiem" and it.start:
                ambiguous = f"{it.start.hour % 12 or 12}:{it.start.minute:02d}"
            specs.append(clar.QuestionSpec(it.key, b, titles.get(it.key, "this activity"), later, prev_title, prev_end, ambiguous))
        prev_blocked = bool(r.blockers)
        if r.placement == "placed":
            prev_title, prev_end = titles.get(it.key), r.end
        else:
            prev_title, prev_end = None, None
    return specs


def _repair_prompt(base: str, errors: str) -> str:
    return f"{base}\n\nYour previous answer did not match the schema. Fix these problems and call the tool again:\n{errors[:1500]}"


async def _call(provider, ctx, inp: PipelineInput, *, max_tokens: int, timeout_s: int, temperature: float):
    req = StructuredRequest(system=ctx.system, user=ctx.user, json_schema=ctx.schema, max_tokens=max_tokens, timeout_s=timeout_s,
                            temperature=temperature, metadata=ctx.metadata)
    resp = await provider.generate_structured(req)
    try:
        return resp, ExtractionOutput.model_validate(resp.data)
    except ValidationError as first:
        req.user = _repair_prompt(ctx.user, str(first))  # one repair call with the validation errors appended (FR-031)
        try:
            resp2 = await provider.generate_structured(req)
        except ProviderOutputError as e:
            raise ExtractionFailed("INVALID_MODEL_OUTPUT") from e
        try:
            return resp2, ExtractionOutput.model_validate(resp2.data)
        except ValidationError as e:
            raise ExtractionFailed("INVALID_MODEL_OUTPUT") from e


async def run_extraction(inp: PipelineInput, provider, *, max_tokens: int = 4096, timeout_s: int = 45, temperature: float = 0.0) -> PipelineResult:
    ctx = build_context(text=inp.text, window_start=inp.window_start, window_end=inp.window_end, now=inp.now, tz=inp.tz, tz_name=inp.tz_name,
                        categories=inp.categories, tags=inp.tags, rules=inp.rules, tasks=inp.open_tasks, hint=inp.hint)
    resp, out = await _call(provider, ctx, inp, max_tokens=max_tokens, timeout_s=timeout_s, temperature=temperature)
    acts = sorted(out.activities, key=lambda a: a.order)[:MAX_ACTIVITIES]
    warnings = list(out.warnings)
    if len(out.activities) > MAX_ACTIVITIES:
        warnings.append(f"Only the first {MAX_ACTIVITIES} activities were kept.")

    cats = {c.id: c for c in inp.categories}
    cat_by_path = {c.path_names: c.id for c in inp.categories}
    root_work = next((c for c in inp.categories if c.root_kind == "work" and " › " not in c.path_names), inp.categories[0])

    prepared: list[dict] = []
    for a in acts:
        flags = set(a.flags)
        # step F: the quote must exist in the text
        qr = verify_quote(inp.text, a.source_quote)
        if not qr.verified:
            flags.add("quote_unverified")
        quote = qr.text if qr.verified else None
        # category: an id from the supplied list, else the closest path, else the Work root with low confidence
        cat_id: uuid.UUID | None = None
        try:
            cid = uuid.UUID(a.category_id)
            cat_id = cid if cid in cats else None
        except ValueError:
            cat_id = None
        ccat = a.confidence.category
        if cat_id is None:
            match = process.extractOne(a.category_id, list(cat_by_path), scorer=fuzz.WRatio, score_cutoff=85) if a.category_id else None
            if match:
                cat_id = cat_by_path[match[0]]
            else:
                cat_id, ccat = root_work.id, min(ccat, 0.3)
                flags.add("category_unresolved")
        # tags and keyword rules; rules look at the activity's own words (whole text when the quote could not be verified)
        haystack = f"{quote or inp.text} {a.title} {a.description or ''}" if quote else inp.text
        cands, cat_override = match_tags(haystack, inp.rules, inp.tags, [t.model_dump() for t in a.tags])
        if cat_override and cat_override in cats:
            cat_id, ccat = cat_override, max(ccat, 0.95)
        # task
        tm = match_task(a.task.model_dump() if a.task else None, inp.open_tasks, a.title, quote or "")
        # invented-time guard (FR-036): a spoken clock time must appear in the quoted words
        ref = a.time_ref.model_copy(deep=True)
        evidence = f"{ref.quote or ''} {a.source_quote or ''}"
        for side in ("start", "end"):
            t = getattr(ref, side)
            if t is not None and not time_supported(t.hour, evidence):
                setattr(ref, side, None)
                flags.add("time_unsupported")
        prepared.append({"a": a, "flags": flags, "quote": quote, "qr": qr, "cat": cat_id, "ccat": ccat, "tags": cands, "task": tm, "ref": ref})

    items = [to_item(p["a"].temp_id, p["ref"].model_dump(mode="json", by_alias=True)) for p in prepared]
    resolved = resolve_day(items, inp.window_start, inp.window_end, inp.tz)

    drafts: list[DraftSpec] = []
    for p, r in zip(prepared, resolved, strict=True):
        a: ExtractedActivity = p["a"]
        flags = set(p["flags"]) | set(r.flags)
        score = conf.final_confidence(a.confidence.overall, a.confidence.time, p["ccat"], flags, unresolved=bool(r.blockers))
        drafts.append(DraftSpec(
            temp_id=a.temp_id, order=a.order, title=a.title.strip()[:120], description=(a.description or None), category_id=p["cat"],
            placement=r.placement, start=r.start, end=r.end, window_start=r.window_start, window_end=r.window_end, duration=r.duration,
            certainty=r.certainty, location_type=a.location_type, confidence=score, flags=sorted(flags), source_quote=p["quote"],
            source_start=p["qr"].start, source_end=p["qr"].end, tags=p["tags"], task=p["task"],
            time_ref=p["ref"].model_dump(mode="json", by_alias=True), llm_conf={**a.confidence.model_dump(), "category": p["ccat"]},
            base_flags=sorted(p["flags"])))

    mark_duplicates(drafts, inp.existing)
    titles = {d.temp_id: d.title for d in drafts}
    questions = clar.build_questions(question_specs(items, resolved, titles), inp.tz)
    return PipelineResult(summary=(out.entry_summary or "").strip()[:120], drafts=drafts, questions=questions, warnings=warnings, llm=resp,
                          parsed=out.model_dump(mode="json", by_alias=True))


def mark_duplicates(drafts: list[DraftSpec], existing: list[Existing]) -> None:
    """FR-044: a likely duplicate of a confirmed activity is unchecked by default and points at the original."""
    placed_existing = [(detectors.Span(str(e.id), e.start, e.end, e.title), e.source_quote) for e in existing if e.placement == "placed" and e.start and e.end]
    for d in drafts:
        hit: str | None = None
        if d.placement == "placed" and d.start and d.end:
            span = detectors.Span(d.temp_id, d.start, d.end, d.title)
            dup = detectors.duplicate_of(span, d.source_quote or "", placed_existing)
            hit = dup.id if dup else None
        elif d.window_start is not None:
            day = [(str(e.id), e.title, e.category_id) for e in existing if e.local_date == d.window_start.date()]
            hit = detectors.unplaced_duplicate(d.title, d.category_id, day)
        if hit:
            d.include, d.duplicate_of = False, uuid.UUID(hit)
            if "possible_duplicate" not in d.flags:
                d.flags.append("possible_duplicate")
