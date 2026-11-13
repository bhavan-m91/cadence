"""Deterministic time resolution (PRD 6.6). The model reports times *as spoken*; this code decides am/pm, midnight
crossings, durations and neighbours. It never invents a number: every placed boundary comes from a spoken time, a
stated duration, a user answer, or a neighbour the model pointed at with an anchor.

Narrative order is the key assumption: people describe a day forwards, so among equally valid am/pm readings the one
that keeps time moving forward from the previous activity wins.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.errors import AppError
from app.core.time import parse_local

LABEL_HOURS = {"morning": (5, 12), "afternoon": (12, 18), "evening": (18, 23), "night": (21, 29)}  # night ends 5am next day
CARRY_OVER = timedelta(hours=12)  # a time may fall up to 12h before the window (sleep that began last night)
JUMP_LIMIT = timedelta(hours=6)  # an am/pm guess that leaves a bigger unexplained jump than this becomes a question


@dataclass(frozen=True)
class Spoken:
    hour: int
    minute: int = 0
    meridiem: str | None = None


@dataclass
class ItemIn:
    key: str
    kind: str = "none"
    start: Spoken | None = None
    end: Spoken | None = None
    start_anchor: str | None = None
    end_anchor: str | None = None
    duration: int | None = None
    approximate: bool = False
    window_label: str | None = None
    day_offset: int = 0
    answers: dict[str, Any] = field(default_factory=dict)


@dataclass
class ItemOut:
    key: str
    placement: str  # placed | unplaced
    start: datetime | None = None
    end: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    duration: int | None = None
    certainty: str = "stated"  # stated | inferred | estimated
    flags: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)  # question types needed: start_time | duration | meridiem


def _local(d: date, minute_of_day: int, tz: ZoneInfo) -> datetime | None:
    extra_days, m = divmod(minute_of_day, 1440)
    try:
        return parse_local(d + timedelta(days=extra_days), time(m // 60, m % 60), tz)
    except AppError:  # a time that does not exist (clock change)
        return None


def _ambiguous(t: Spoken) -> bool:
    return t.meridiem is None and 1 <= t.hour <= 12


def candidates(t: Spoken, dates: list[date], tz: ZoneInfo) -> list[datetime]:
    if t.meridiem == "am":
        hours = [t.hour % 12]
    elif t.meridiem == "pm":
        hours = [t.hour % 12 + 12]
    elif t.hour == 0 or t.hour > 12:
        hours = [t.hour % 24]
    else:
        hours = sorted({t.hour % 12, t.hour % 12 + 12})
    out = []
    for d in dates:
        for h in hours:
            inst = _local(d, h * 60 + t.minute, tz)
            if inst is not None:
                out.append(inst)
    return sorted(out)


def _exact(h: int, m: int) -> Spoken:
    """A 24-hour answer from the user is exact, never an am/pm guess."""
    return Spoken(h, m, "am" if h < 12 else "pm")


def _parse_hhmm(v: str) -> tuple[int, int] | None:
    try:
        h, m = v.split(":")
        h, m = int(h), int(m)
        return (h, m) if 0 <= h < 24 and 0 <= m < 60 else None
    except (ValueError, AttributeError):
        return None


class _Ctx:
    def __init__(self, w0: datetime, w1: datetime, tz: ZoneInfo):
        self.w0, self.w1, self.tz = w0, w1, tz
        base = w0.astimezone(tz).date()
        self.base = base

    def dates(self, day_offset: int) -> list[date]:
        return [self.base + timedelta(days=day_offset + k) for k in (-1, 0, 1)]


def _pick(ctx: _Ctx, t: Spoken, lo: datetime, day_offset: int, label: str | None, hi: datetime | None = None,
          has_prev: bool = False) -> tuple[datetime | None, list[str], bool]:
    """Choose an instant for a spoken time. Returns (instant, flags, ambiguous_question_needed)."""
    hi = hi or ctx.w1
    cands = candidates(t, ctx.dates(day_offset), ctx.tz)
    inside = [c for c in cands if lo <= c <= hi]
    flags: list[str] = []
    if not inside:  # carried over from before the window (sleep) or before the cursor
        loose = [c for c in cands if ctx.w0 - CARRY_OVER <= c <= hi]
        if not loose:
            return None, ["outside_window"], False
        inside = [loose[-1]]
        flags.append("outside_window" if inside[0] < ctx.w0 else "before_cursor")
    ambiguous = _ambiguous(t)
    if len(inside) > 1 and ambiguous and label:
        want_am = label == "morning"
        narrowed = [c for c in inside if (c.astimezone(ctx.tz).hour < 12) == want_am]
        inside = narrowed or inside
    chosen = inside[0]
    question = False
    if ambiguous:
        flags.append("meridiem_inferred")
        if has_prev and len(inside) > 1 and (chosen - lo) > JUMP_LIMIT:
            question = True  # the earlier reading leaves a big jump after the previous activity: ask instead of guessing
    return chosen, flags, question


def _label_window(ctx: _Ctx, label: str | None, lo: datetime) -> tuple[datetime, datetime]:
    start, end = lo, ctx.w1
    if label in LABEL_HOURS:
        h0, h1 = LABEL_HOURS[label]
        base = ctx.base
        a = _local(base, h0 * 60, ctx.tz)
        b = _local(base, h1 * 60, ctx.tz)
        if a and b:
            start, end = max(lo, a), min(ctx.w1, b)
    if end <= start:  # nothing left of the label inside the window: fall back to the whole remainder
        start, end = lo, max(ctx.w1, lo + timedelta(minutes=1))
    return start, end


def resolve_day(items: list[ItemIn], window_start: datetime, window_end: datetime, tz: ZoneInfo) -> list[ItemOut]:
    ctx = _Ctx(window_start, window_end, tz)
    out: list[ItemOut] = []
    cursor = window_start
    prev_end: datetime | None = None
    ordered = list(items)

    def next_start_of(i: int) -> datetime | None:
        """The start of the next activity if it is stated by number or answer (never guessed)."""
        for nxt in ordered[i + 1:]:
            ans = nxt.answers.get("start")
            if ans and _parse_hhmm(ans):
                h, m = _parse_hhmm(ans)  # type: ignore[misc]
                got, _, _ = _pick(ctx, _exact(h, m), cursor, nxt.day_offset, None)
                return got
            if nxt.start:
                got, _, _ = _pick(ctx, nxt.start, cursor, nxt.day_offset, nxt.window_label)
                return got
            return None
        return None

    for i, it in enumerate(ordered):
        res = ItemOut(key=it.key, placement="placed")
        ans = it.answers
        duration = ans.get("duration") or it.duration
        if ans.get("duration") and ans.get("duration_estimated"):
            res.certainty = "estimated"
        if it.approximate:
            res.flags.append("approximate")
        start = end = None
        start_stated_by_user = False

        # ---- start
        a_start = _parse_hhmm(ans["start"]) if ans.get("start") else None
        spoken_start = _exact(*a_start) if a_start else it.start
        if a_start:
            start_stated_by_user = True
        if spoken_start is not None:
            st = spoken_start
            if ans.get("meridiem") in ("am", "pm") and st.meridiem is None:
                st = Spoken(st.hour, st.minute, ans["meridiem"])
            start, fl, q = _pick(ctx, st, cursor, it.day_offset, it.window_label, has_prev=prev_end is not None)
            res.flags += fl
            if q:
                res.blockers.append("meridiem")
        elif it.start_anchor == "previous_end":
            if prev_end is not None:
                start = prev_end
                res.certainty = "inferred" if res.certainty == "stated" else res.certainty
                res.flags.append("boundary_inferred")
            else:
                res.flags.append("start_unknown")

        # ---- end
        if it.end is not None:
            et = it.end
            if ans.get("meridiem") in ("am", "pm") and et.meridiem is None and not (it.start and _ambiguous(it.start)):
                et = Spoken(et.hour, et.minute, ans["meridiem"])
            lo = (start + timedelta(minutes=1)) if start else cursor
            cands = [c for c in candidates(et, ctx.dates(it.day_offset), tz) if c >= lo]
            inside = [c for c in cands if c <= window_end]
            pool = inside or [c for c in cands if start is not None and c <= start + timedelta(hours=24)]
            if pool:
                end = pool[0]
                if _ambiguous(et):
                    res.flags.append("meridiem_inferred")
                if not inside:
                    res.flags.append("extends_past_window")
            elif start is not None:
                res.flags.append("end_before_start")
        elif it.end_anchor == "next_start":
            nxt = next_start_of(i)
            if nxt is not None and (start is None or nxt > start):
                end = nxt
                res.certainty = "inferred" if res.certainty == "stated" else res.certainty
                res.flags.append("boundary_inferred")

        # ---- combine
        if start is not None and end is not None:
            res.start, res.end = start, end
            res.duration = int((end - start).total_seconds() // 60)
        elif start is not None and duration:
            res.start, res.end, res.duration = start, start + timedelta(minutes=duration), duration
        elif end is not None and duration:
            res.start, res.end, res.duration = end - timedelta(minutes=duration), end, duration
        else:
            res.placement = "unplaced"

        if res.placement == "placed" and res.duration is not None and not (1 <= res.duration <= 1440):
            res.placement, res.start, res.end, res.duration = "unplaced", None, None, None
            res.flags.append("end_before_start")

        if res.placement == "unplaced":
            res.flags.append("unplaced")
            res.duration = duration
            if start is not None:  # a start with no end and no duration
                res.window_start, res.window_end = start, max(window_end, start + timedelta(minutes=1))
                res.blockers.append("duration")
                res.flags.append("missing_duration")
            elif end is not None:  # an end with no start (chain broken upstream)
                res.window_start, res.window_end = min(cursor, end - timedelta(minutes=1)), end
                res.blockers.append("start_time")
                res.flags.append("start_unknown")
            else:
                res.window_start, res.window_end = _label_window(ctx, it.window_label, cursor)
                res.blockers.append("start_time" if duration else "duration")
                if not duration:
                    res.flags.append("missing_duration")
            if res.duration and res.window_end and res.window_start and res.duration > int((res.window_end - res.window_start).total_seconds() // 60):
                res.window_end = res.window_start + timedelta(minutes=res.duration)  # never claim a window smaller than the duration
        else:
            cursor = max(cursor, res.end)  # type: ignore[arg-type]
            prev_end = res.end
            if start_stated_by_user and "boundary_inferred" in res.flags:
                res.flags.remove("boundary_inferred")
        if ans.get("keep_unplaced") and res.placement == "unplaced" and "start_time" in res.blockers:
            res.blockers.remove("start_time")  # the person chose "some time in that window": a valid, honest record
        if "meridiem" in res.blockers and "meridiem_ambiguous" not in res.flags:
            res.flags.append("meridiem_ambiguous")
        if res.placement == "unplaced":
            prev_end = None if res.end is None else prev_end
        out.append(res)
    return out
