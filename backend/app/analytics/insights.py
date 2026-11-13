"""Banners from fixed rules (FR-135). No model is involved: each rule is a threshold and a sentence."""

from dataclasses import dataclass
from datetime import date

from app.core.time import ymd_label

MAX_BANNERS = 3
DAY_DELTA_MIN = 30
WEEK_DELTA_MIN = 120


@dataclass
class Banner:
    id: str
    kind: str  # coverage | ideal | tag_cap | sleep
    severity: str  # warn | bad
    text: str
    action_label: str
    action_route: str
    priority: int


def hm(minutes: int) -> str:
    h, m = divmod(abs(round(minutes)), 60)
    return f"{h}h {m}m" if h and m else f"{h}h" if h else f"{m}m"


def coverage_banner(day: date, logged: int, elapsed: int) -> Banner:
    return Banner(f"cov-{day.isoformat()}", "coverage", "bad", f"{ymd_label(day)} adds up to {hm(logged)}, not {hm(elapsed)}.", "Fill gaps", f"/calendar?date={day.isoformat()}", 0)


def ideal_banners(rows: list[dict], scope: str) -> list[Banner]:
    """One banner for the biggest over and the biggest under, when it clears the threshold for the scope."""
    floor = DAY_DELTA_MIN if scope == "day" else WEEK_DELTA_MIN
    out: list[Banner] = []
    over = max((r for r in rows if r["delta"] >= floor), key=lambda r: r["delta"], default=None)
    under = min((r for r in rows if r["delta"] <= -floor), key=lambda r: r["delta"], default=None)
    if over:
        out.append(Banner(f"over-{over['category_id']}", "ideal", "warn", f"{over['name']} is {hm(over['delta'])} over its Ideal {'today' if scope == 'day' else 'so far this week'}.", "Open Ideal", "/ideal", 2))
    if under:
        out.append(Banner(f"under-{under['category_id']}", "ideal", "warn", f"{under['name']} is {hm(-under['delta'])} under its Ideal {'today' if scope == 'day' else 'so far this week'}.", "Open Ideal", "/ideal", 3))
    return out


def tag_cap_banner(name: str, tag_id: str, minutes: int, cap: int) -> Banner:
    return Banner(f"cap-{tag_id}", "tag_cap", "bad", f"#{name} is {hm(minutes - cap)} over its weekly cap of {hm(cap)}.", "See tag", f"/tags?tag={tag_id}", 1)


def sleep_banner(short_nights: int) -> Banner:
    return Banner("sleep-short", "sleep", "warn", f"{short_nights} short nights in the last 7.", "See sleep", "/overview", 4)


def pick(banners: list[Banner]) -> list[Banner]:
    return sorted(banners, key=lambda b: b.priority)[:MAX_BANNERS]
