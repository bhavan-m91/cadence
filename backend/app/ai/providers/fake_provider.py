"""Offline providers. `FakeProvider` is a small heuristic extractor so the whole journal flow works with no API key
(demo mode). `FixtureProvider` replays canned model output for tests and the evaluation harness."""

import re
import time

from app.ai.providers.base import StructuredRequest, StructuredResponse

_CONNECT = re.compile(r"^(?:and\s+then|and|then|after\s+that|afterwards|so|later|next|but)\b[\s,]*", re.I)
_SPLIT = re.compile(r"(?<=[.!?])\s+|\s+(?=(?:and\s+then|then|after\s+that|afterwards)\b)", re.I)
_TIME = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
_RANGE = re.compile(rf"(?:from\s+)?{_TIME}\s*(?:to|until|till|-|–)\s*{_TIME}(?!\d)", re.I)
_UNTIL = re.compile(rf"\b(?:until|till)\s+{_TIME}", re.I)
_AT = re.compile(rf"\b(?:at|around|about|by)\s+{_TIME}", re.I)
_DUR = re.compile(r"(?:for\s+)?(?:(?:about|around|roughly)\s+)?(?P<n>\d+(?:\.\d+)?|an?|half an?)\s*(?P<u>hours?|hrs?|minutes?|mins?)\b", re.I)
_HALF_HOUR = re.compile(r"\bhalf an hour\b", re.I)
_AN_HOUR = re.compile(r"\b(?:an|one) hour\b", re.I)
_LABEL = re.compile(r"\b(morning|afternoon|evening|night)\b", re.I)
_APPROX = re.compile(r"\b(around|about|roughly|approximately)\b", re.I)
_VERBS = re.compile(r"\b(worked|work|started|woke|slept|sleep|had|attended|went|spent|met|called|took|read|watched|scrolled|wasted|cooked|ate|drove|walked|ran|debugged|fixed|wrote|reviewed|researched|brainstormed|played|studied|cleaned|shopped|left|reached|joined|finished|did)\b", re.I)

_CATEGORY_KEYWORDS = [
    ("sleep", ["slept", "sleep", "nap", "went to bed"]),
    ("meal", ["lunch", "dinner", "breakfast", "ate ", "snack", "cooked", "cooking"]),
    ("meeting", ["meeting", "call", "standup", "stand-up", "sync", "interview", "1:1"]),
    ("health", ["gym", "workout", "yoga", "exercise", "swim", "ran ", "run ", "walk"]),
    ("commute", ["commute", "metro", "drove", "drive", "train", "flight", "cab ", "bus "]),
    ("entertainment", ["instagram", "youtube", "netflix", "series", "movie", "scroll", "twitter", "game", "tv ", "wasted"]),
    ("learning", ["read ", "reading", "course", "study", "studied", "learn", "lecture", "book"]),
    ("admin", ["email", "emails", "invoice", "admin", "paperwork", "expenses", "tax"]),
    ("family", ["family", "friends", "friend", "parents", "kids", "party"]),
]
_NAME_HINTS = {"meal": ["meal"], "meeting": ["meeting"], "health": ["health"], "commute": ["commute"], "entertainment": ["entertain"],
               "learning": ["learn"], "admin": ["admin"], "family": ["family", "friend"]}
_WORKY = re.compile(r"\b(work|debug|code|coding|fix|research|write|wrote|design|implement|review|brainstorm|deploy|ship|api|bug|database)\w*", re.I)


def _to_hour(h: str, mer: str | None) -> dict | None:
    hour = int(h)
    if hour > 24:
        return None
    return {"hour": hour % 24 if not mer else hour, "meridiem": (mer.lower().replace(".", "")[0] + "m") if mer else None}


def _tod(h: str, m: str | None, mer: str | None) -> dict | None:
    base = _to_hour(h, mer)
    if base is None:
        return None
    base["minute"] = int(m) if m else 0
    return base


def _pick_category(span: str, cats: list[dict]) -> tuple[str, float]:
    low = span.lower() + " "
    for kind, words in _CATEGORY_KEYWORDS:
        if any(w in low for w in words):
            if kind == "sleep":
                c = next((c for c in cats if "sleep" in c["path"].lower()), None)
            else:
                c = next((c for c in cats if any(h in c["path"].lower().split(" › ")[-1] for h in _NAME_HINTS[kind])), None)
            if c:
                return c["id"], 0.85
    if _WORKY.search(span):
        c = next((c for c in cats if c.get("focus")), None) or next((c for c in cats if c["path"].lower().startswith("work")), None)
        if c:
            return c["id"], 0.8
    c = next((c for c in cats if c["path"].lower().startswith("personal") and " › " not in c["path"]), None) or cats[0]
    return c["id"], 0.45


class FakeProvider:
    name = "fake"
    model = "offline-demo"

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        started = time.perf_counter()
        meta = request.metadata
        text: str = meta["text"]
        cats, tags = meta["categories"], meta["tags"]
        acts, order = [], 0
        for sentence_match in re.finditer(r"[^.!?\n]+[.!?]?", text):
            for span, start in self._segments(sentence_match.group(0), sentence_match.start(), text):
                act = self._activity(span, order + 1, acts, cats, tags)
                if act:
                    order += 1
                    act["_span"] = (start, start + len(span))
                    acts.append(act)
        acts = self._merge_point_with_duration(acts, text)
        data = {"schema_version": "1", "entry_summary": (acts[0]["title"] + (f" and {len(acts) - 1} more" if len(acts) > 1 else ""))[:120] if acts else "Nothing to log",
                "activities": acts, "warnings": [] if acts else ["No activities were found in this entry."]}
        return StructuredResponse(data=data, raw={"fake": True}, input_tokens=len(text) // 4, output_tokens=len(str(data)) // 4,
                                  latency_ms=int((time.perf_counter() - started) * 1000), model=self.model, provider=self.name)

    @staticmethod
    def _merge_point_with_duration(acts: list[dict], text: str) -> list[dict]:
        """"Started at 9:30. Spent an hour researching X." is one activity: a start time, then how long and what."""
        merged: list[dict] = []
        for a in acts:
            prev = merged[-1] if merged else None
            if (prev and prev["time_ref"]["kind"] == "point" and a["time_ref"]["kind"] == "duration" and "start_anchor" not in a["time_ref"]
                    and a["_span"][0] - prev["_span"][1] < 3):
                prev["time_ref"].update(kind="range", duration_minutes=a["time_ref"]["duration_minutes"], approximate=prev["time_ref"]["approximate"] or a["time_ref"]["approximate"])
                prev["title"], prev["category_id"], prev["tags"] = a["title"], a["category_id"], a["tags"]
                prev["confidence"] = a["confidence"]
                prev["_span"] = (prev["_span"][0], a["_span"][1])
                prev["source_quote"] = text[prev["_span"][0]:prev["_span"][1]].strip(" ,;")
                continue
            merged.append(a)
        for i, a in enumerate(merged, 1):
            a["order"], a["temp_id"] = i, f"a{i}"
            a.pop("_span", None)
        return merged

    @staticmethod
    def _segments(sentence: str, offset: int, full: str):
        pieces = [p for p in _SPLIT.split(sentence) if p and p.strip()]
        pos = 0
        for p in pieces:
            i = sentence.find(p, pos)
            pos = i + len(p)
            span = p.strip()
            if span:
                yield span, offset + i

    def _activity(self, span: str, order: int, previous: list[dict], cats: list[dict], tags: list[dict]) -> dict | None:
        body = _CONNECT.sub("", span).strip(" ,;.")
        if not body or not (_VERBS.search(body) or _RANGE.search(body) or _AT.search(body) or _DUR.search(body)):
            return None
        chained = bool(_CONNECT.match(span)) and bool(previous)
        approx = bool(_APPROX.search(body))
        ref: dict = {"kind": "none", "approximate": approx, "day_offset": 0, "quote": None}
        m = _RANGE.search(body)
        until = _UNTIL.search(body)
        at = _AT.search(body)
        dur = self._duration(body)
        if m and not (m.group(3) is None and m.group(6) is None and int(m.group(1)) > 24):
            s, e = _tod(m.group(1), m.group(2), m.group(3)), _tod(m.group(4), m.group(5), m.group(6))
            if s and e:
                ref.update(kind="range", start=s, end=e, quote=m.group(0))
        elif until:
            ref.update(kind="range", end=_tod(until.group(1), until.group(2), until.group(3)), quote=until.group(0))
            if chained or previous:
                ref["start_anchor"] = "previous_end"
            if dur:
                ref["duration_minutes"] = dur
        elif at:
            ref.update(kind="range" if dur else "point", start=_tod(at.group(1), at.group(2), at.group(3)), quote=at.group(0))
            if dur:
                ref["duration_minutes"] = dur
        elif dur:
            lab = _LABEL.search(body)
            ref.update(kind="duration" if chained else ("vague" if lab else "duration"), duration_minutes=dur, quote=body)
            if chained:
                ref["start_anchor"] = "previous_end"
            if lab:
                ref["window"] = {"label": lab.group(1).lower()}
        else:
            lab = _LABEL.search(body)
            if lab:
                ref.update(kind="vague", window={"label": lab.group(1).lower()}, quote=lab.group(0))
        cat_id, ccat = _pick_category(body, cats)
        tag_props = []
        for t in tags:
            variants = {t["name"], t["name"].replace("-", " ")}
            if any(re.search(rf"(?<!\w){re.escape(v)}(?!\w)", body, re.I) for v in variants):
                tag_props.append({"tag_id": t["id"], "name": t["name"], "reason": t["name"], "confidence": 0.9})
        title = re.sub(r"\s+", " ", body)
        for pat in (_RANGE, _UNTIL, _AT):
            title = pat.sub("", title)
        title = re.sub(r"\b(?:for\s+)?(?:about|around)?\s*\d+\s*(?:hours?|minutes?|mins?)\b|\bfor an hour\b|\bhalf an hour\b", "", title, flags=re.I)
        title = re.sub(r"^(?:i\s+)?(?:started my day|woke up)?\s*", "", title, flags=re.I).strip(" ,;.-") or body
        title = (title[:1].upper() + title[1:])[:80]
        known = 0.85 if ref["kind"] in ("range", "point") else 0.6
        return {"temp_id": f"a{order}", "order": order, "title": title, "description": None, "source_quote": span.strip(" ,;"), "category_id": cat_id,
                "time_ref": ref, "tags": tag_props, "task": None, "location_type": None,
                "confidence": {"overall": min(ccat, known + 0.05), "time": known, "category": ccat}, "flags": []}

    @staticmethod
    def _duration(body: str) -> int | None:
        if _HALF_HOUR.search(body):
            return 30
        if _AN_HOUR.search(body):
            return 60
        m = _DUR.search(body)
        if not m:
            return None
        n = m.group("n").lower()
        val = 30 if n.startswith("half") else 1 if n in ("a", "an") else float(n)
        return int(round(val * (60 if m.group("u").lower().startswith("h") else 1)))


class FixtureProvider:
    """Replays a fixed model response (a dict, or a list consumed one per call) for tests and the eval harness."""

    name = "fixture"
    model = "fixture-1"

    def __init__(self, responses: dict | list[dict]):
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.requests: list[StructuredRequest] = []

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        self.requests.append(request)
        data = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return StructuredResponse(data=data, raw={"fixture": True}, input_tokens=100, output_tokens=50, latency_ms=5, model=self.model, provider=self.name)
