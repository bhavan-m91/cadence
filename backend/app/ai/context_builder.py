"""Assembles what the model sees (PRD 6.4). Never sent: email, name, account id, other entries, analytics (FR-056)."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined

from app.ai.tag_matcher import RuleInfo, TagInfo, phrase_in
from app.ai.task_matcher import OpenTask

PROMPT_NAME = "extract_activities"
PROMPT_VERSION = "1.0.0"
PROMPT_ID = f"{PROMPT_NAME}@{PROMPT_VERSION}"
PROMPT_DIR = Path(__file__).parent / "prompts" / PROMPT_NAME / f"v{PROMPT_VERSION}"
MAX_TAGS = 150
MAX_TASKS = 30
MAX_TEXT = 10_000


@dataclass
class CategoryInfo:
    id: "uuid.UUID"  # noqa: F821
    name: str
    path_names: str
    root_kind: str
    description: str | None = None
    counts_as_focus: bool = False
    is_transition: bool = False


@dataclass
class LlmContext:
    system: str
    user: str
    schema: dict
    metadata: dict = field(default_factory=dict)  # structured copy for the offline provider; never logged


_env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)


def load_system() -> str:
    return (PROMPT_DIR / "system.md").read_text()


def load_schema() -> dict:
    return json.loads((PROMPT_DIR / "schema.json").read_text())


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


def select_tags(tags: list[TagInfo], text: str) -> list[TagInfo]:
    active = [t for t in tags if not t.archived and t.merged_into_id is None]
    if len(active) <= MAX_TAGS:
        return active
    hits = [t for t in active if phrase_in(text, t.name) or any(phrase_in(text, a) for a in t.aliases)]
    return (hits + [t for t in active if t not in hits])[:MAX_TAGS]


def select_tasks(tasks: list[OpenTask], text: str) -> list[OpenTask]:
    words = _words(text)
    return sorted(tasks, key=lambda t: -len(_words(t.title) & words))[:MAX_TASKS]


def build_context(*, text: str, window_start: datetime, window_end: datetime, now: datetime, tz: ZoneInfo, tz_name: str,
                  categories: list[CategoryInfo], tags: list[TagInfo], rules: list[RuleInfo], tasks: list[OpenTask],
                  hint: str | None, tag_names_by_id: dict | None = None) -> LlmContext:
    text = text[:MAX_TEXT]
    fmt = "%a %d %b %Y, %H:%M"
    cats = [{"id": str(c.id), "path": c.path_names, "description": c.description, "focus": c.counts_as_focus} for c in categories]
    sel_tags = select_tags(tags, text)
    tag_rows = [{"id": str(t.id), "name": t.name, "aliases": t.aliases} for t in sel_tags]
    task_rows = [{"id": str(t.id), "title": t.title, "project": t.project, "priority": t.priority} for t in select_tasks(tasks, text)]
    names = {t.id: t.name for t in tags}
    cat_names = {c.id: c.path_names for c in categories}
    hits = []
    for r in rules:
        if phrase_in(text, r.phrase):
            target = f"#{names.get(r.target_id, '?')}" if r.target_type == "tag" else cat_names.get(r.target_id, "?")
            hits.append({"phrase": r.phrase, "target": target})
    user = _env.from_string((PROMPT_DIR / "user.md.j2").read_text()).render(
        timezone=tz_name, window_start_local=window_start.astimezone(tz).strftime(fmt), window_end_local=window_end.astimezone(tz).strftime(fmt),
        now_local=now.astimezone(tz).strftime(fmt), entry_date=window_start.astimezone(tz).date().isoformat(), hint=(hint or "").strip()[:500] or None,
        categories=cats, tags=tag_rows, keyword_hits=hits, tasks=task_rows, text=text)
    return LlmContext(system=load_system(), user=user, schema=load_schema(),
                      metadata={"text": text, "categories": cats, "tags": tag_rows, "tasks": task_rows})
