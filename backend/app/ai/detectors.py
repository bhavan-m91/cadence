"""Deterministic gap, overlap and duplicate detection (PRD 6.10). Pure computation on intervals."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz

DUP_OVERLAP = 0.80
DUP_TITLE = 0.85


@dataclass
class Span:
    id: str
    start: datetime
    end: datetime
    title: str = ""


@dataclass
class Conflict:
    draft_id: str
    other_id: str
    other_title: str
    other_is_draft: bool
    start: datetime
    end: datetime
    overlap_minutes: int


def minutes(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def gaps(spans: list[tuple[datetime, datetime]], w0: datetime, w1: datetime, min_minutes: int) -> list[tuple[datetime, datetime]]:
    """The complement of placed intervals inside the coverage window; short gaps are dropped (FR-042)."""
    out, cursor = [], w0
    for s, e in sorted(spans):
        if s > cursor:
            out.append((cursor, min(s, w1)))
        cursor = max(cursor, e)
    if cursor < w1:
        out.append((cursor, w1))
    return [(a, b) for a, b in out if b > a and minutes(a, b) >= min_minutes]


def overlaps(drafts: list[Span], existing: list[Span]) -> list[Conflict]:
    found: list[Conflict] = []
    for i, d in enumerate(drafts):
        for e in existing:
            if d.start < e.end and e.start < d.end:
                s, t = max(d.start, e.start), min(d.end, e.end)
                found.append(Conflict(d.id, e.id, e.title, False, s, t, minutes(s, t)))
        for o in drafts[i + 1:]:
            if d.start < o.end and o.start < d.end:
                s, t = max(d.start, o.start), min(d.end, o.end)
                found.append(Conflict(d.id, o.id, o.title, True, s, t, minutes(s, t)))
    return found


def title_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100


def duplicate_of(d: Span, quote: str, existing: list[tuple[Span, str | None]]) -> Span | None:
    """Time overlap >= 80% of the shorter interval AND (title similarity >= 0.85 OR identical source quote) (FR-044)."""
    shorter = lambda a, b: min(minutes(a.start, a.end), minutes(b.start, b.end)) or 1  # noqa: E731
    for e, e_quote in existing:
        if d.start < e.end and e.start < d.end:
            ov = minutes(max(d.start, e.start), min(d.end, e.end))
            if ov / shorter(d, e) >= DUP_OVERLAP and (title_similarity(d.title, e.title) >= DUP_TITLE or (quote and quote == e_quote)):
                return e
    return None


def unplaced_duplicate(title: str, category_id: uuid.UUID, same_day: list[tuple[str, str, uuid.UUID]]) -> str | None:
    """Unplaced candidates compare on date, category and title only. `same_day` rows: (activity id, title, category id)."""
    for aid, t, cid in same_day:
        if cid == category_id and title_similarity(title, t) >= DUP_TITLE:
            return aid
    return None
