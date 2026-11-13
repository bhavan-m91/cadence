"""Clarification questions are raised by code, at most 5 per run, ranked by how much depends on the answer (FR-041).
Answers are applied by code too: no second LLM call (D-17)."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

MAX_QUESTIONS = 5
DURATION_CHOICES = [15, 30, 60]


@dataclass
class QuestionSpec:
    temp_id: str
    qtype: str  # start_time | duration | meridiem
    title: str
    dependents: int = 0
    prev_title: str | None = None
    prev_end: datetime | None = None
    ambiguous_time: str | None = None  # e.g. "9:30"


def _clock(dt: datetime, tz: ZoneInfo) -> str:
    l = dt.astimezone(tz)
    h = l.hour % 12 or 12
    return f"{h}:{l.minute:02d} {'am' if l.hour < 12 else 'pm'}"


def build_questions(specs: list[QuestionSpec], tz: ZoneInfo) -> list[dict]:
    ranked = sorted(specs, key=lambda s: (-s.dependents, s.temp_id))[:MAX_QUESTIONS]
    out = []
    for s in ranked:
        qid = f"{s.qtype}:{s.temp_id}"
        if s.qtype == "start_time":
            opts = []
            if s.prev_end is not None:
                opts.append({"label": f"Right after {s.prev_title or 'the last one'} ({_clock(s.prev_end, tz)})", "value": s.prev_end.astimezone(tz).strftime("%H:%M")})
            opts.append({"label": "Enter a time", "value": "custom"})
            opts.append({"label": "Keep it as “some time” in that window", "value": "unplaced"})
            out.append({"id": qid, "type": "start_time", "activity_temp_id": s.temp_id, "prompt": f"When did “{s.title}” start?", "options": opts})
        elif s.qtype == "duration":
            opts = [{"label": f"About {m} min" if m < 60 else "About an hour", "value": f"estimate:{m}"} for m in DURATION_CHOICES]
            opts.append({"label": "Enter minutes", "value": "custom"})
            out.append({"id": qid, "type": "duration", "activity_temp_id": s.temp_id, "prompt": f"How long was “{s.title}”?", "options": opts})
        elif s.qtype == "meridiem":
            t = s.ambiguous_time or ""
            out.append({"id": qid, "type": "meridiem", "activity_temp_id": s.temp_id, "prompt": f"Was “{s.title}” at {t} am or pm?",
                        "options": [{"label": f"{t} am", "value": "am"}, {"label": f"{t} pm", "value": "pm"}]})
    return out


def apply_answer(answers: dict, question: dict, value: str) -> dict:
    """Merge one answer into the per-activity answer map. Returns the updated map; raises ValueError for a bad value."""
    tid = question["activity_temp_id"]
    cur = dict(answers.get(tid, {}))
    t = question["type"]
    if t == "start_time" and value == "unplaced":
        cur["keep_unplaced"] = True
    elif t == "start_time":
        v = value.removeprefix("custom:")
        h, m = v.split(":")
        if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError("bad time")
        cur["start"] = f"{int(h):02d}:{int(m):02d}"
    elif t == "duration":
        if value.startswith("estimate:"):
            cur["duration"], cur["duration_estimated"] = int(value.split(":")[1]), True
        else:
            n = int(value.removeprefix("custom:"))
            if not 1 <= n <= 1440:
                raise ValueError("bad duration")
            cur["duration"], cur["duration_estimated"] = n, False
    elif t == "meridiem":
        if value not in ("am", "pm"):
            raise ValueError("bad meridiem")
        cur["meridiem"] = value
    else:
        raise ValueError("unknown question type")
    return {**answers, tid: cur}
