"""Evaluation harness (PRD 6, 12): run labelled journal days through the real pipeline and score the PRD's release gates.

    python -m app.ai.eval.run_eval --provider fake|anthropic [--verbose]

Gates: activity recall >= 0.85, time-placement precision >= 0.90, invented-time rate == 0.
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ai.context_builder import CategoryInfo
from app.ai.extraction_pipeline import PipelineInput, run_extraction
from app.ai.tag_matcher import TagInfo
from app.core.config import get_settings
from app.core.time import parse_local

TZ = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 13)
DATASET = Path(__file__).parent / "dataset" / "cases.jsonl"
CATEGORY_TREE = [("Work", None, "work"), ("Deep work", "Work", "work"), ("Meetings", "Work", "work"), ("Sales & clients", "Work", "work"), ("Admin", "Work", "work"),
                 ("Learning", "Work", "work"), ("Personal", None, "personal"), ("Health", "Personal", "personal"), ("Family & friends", "Personal", "personal"),
                 ("Meals & chores", "Personal", "personal"), ("Commute", "Personal", "personal"), ("Entertainment", "Personal", "personal"), ("Sleep", None, "sleep")]


def taxonomy() -> list[CategoryInfo]:
    cats = []
    for name, parent, root in CATEGORY_TREE:
        cats.append(CategoryInfo(uuid.uuid5(uuid.NAMESPACE_DNS, name), name, f"{parent} › {name}" if parent else name, root, counts_as_focus=name in ("Deep work", "Learning")))
    return cats


def hhmm(dt: datetime | None) -> str | None:
    return dt.astimezone(TZ).strftime("%H:%M") if dt else None


async def run(provider, verbose: bool) -> dict:
    stats = {"expected": 0, "found": 0, "expected_times": 0, "correct_times": 0, "placed": 0, "invented": 0, "cases": 0}
    tags = [TagInfo(uuid.uuid4(), n) for n in ("product-b", "social-media", "research", "bug")]
    for line in DATASET.read_text().splitlines():
        case = json.loads(line)
        h0, h1 = case["window"].split("-")
        w0 = parse_local(DAY, time(*map(int, h0.split(":"))), TZ)
        w1 = parse_local(DAY, time(*map(int, h1.split(":"))), TZ)
        inp = PipelineInput(text=case["text"], window_start=w0, window_end=w1, tz=TZ, tz_name="Asia/Kolkata", now=datetime.now(UTC), categories=taxonomy(),
                            tags=tags, rules=[], open_tasks=[], gap_min_minutes=10)
        stats["cases"] += 1
        try:
            res = await run_extraction(inp, provider)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {case['id']}: pipeline failed ({type(e).__name__})")
            stats["expected"] += len(case["expect"])
            stats["expected_times"] += sum(1 for x in case["expect"] if x.get("placement") != "unplaced")
            continue
        used: set[str] = set()
        for exp in case["expect"]:
            stats["expected"] += 1
            wants_time = exp.get("placement") != "unplaced"
            stats["expected_times"] += int(wants_time)
            hit = next((d for d in res.drafts if d.temp_id not in used and exp["match"] in (d.title + " " + (d.source_quote or "")).lower()), None)
            if hit is None:
                if verbose:
                    print(f"  - {case['id']}: no activity matching '{exp['match']}'")
                continue
            used.add(hit.temp_id)
            stats["found"] += 1
            if wants_time:
                ok = hit.placement == "placed" and hhmm(hit.start) == exp["start"] and (exp.get("end") is None or hhmm(hit.end) == exp["end"])
                stats["correct_times"] += int(ok)
                if verbose and not ok:
                    print(f"  - {case['id']}: '{exp['match']}' expected {exp['start']}-{exp.get('end')} got {hit.placement} {hhmm(hit.start)}-{hhmm(hit.end)}")
            elif hit.placement == "placed":
                stats["invented"] += 1  # the text supports no time, yet one was placed
                if verbose:
                    print(f"  - {case['id']}: '{exp['match']}' should be unplaced but was placed {hhmm(hit.start)}-{hhmm(hit.end)}")
        stats["placed"] += sum(1 for d in res.drafts if d.placement == "placed")
        if not case["expect"] and res.drafts and verbose:
            print(f"  - {case['id']}: expected no activities, got {[d.title for d in res.drafts]}")
    return stats


def report(s: dict) -> bool:
    recall = s["found"] / s["expected"] if s["expected"] else 1
    precision = s["correct_times"] / s["expected_times"] if s["expected_times"] else 1
    gates = [("activity recall", recall, recall >= 0.85, ">= 0.85"), ("time placement precision", precision, precision >= 0.90, ">= 0.90"),
             ("invented times", s["invented"], s["invented"] == 0, "== 0")]
    print(f"\n{s['cases']} cases, {s['expected']} expected activities")
    for name, val, ok, rule in gates:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {val:.2f}  (gate {rule})" if isinstance(val, float) else f"  {'PASS' if ok else 'FAIL'}  {name}: {val}  (gate {rule})")
    return all(g[2] for g in gates)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.provider == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider

        s = get_settings()
        if not s.anthropic_api_key:
            print("ANTHROPIC_API_KEY is not set (backend/.env)")
            return 2
        provider = AnthropicProvider(s.anthropic_api_key, s.llm_model_extract)
        print(f"Running {DATASET.name} against {provider.model}")
    else:
        from app.ai.providers.fake_provider import FakeProvider

        provider = FakeProvider()
        print("Running against the offline demo extractor (expect low scores: it is a heuristic, not a model)")
    return 0 if report(await run(provider, args.verbose)) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
