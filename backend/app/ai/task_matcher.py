"""Task linking: the model proposes an id, code checks similarity >= 0.80 (FR-081)."""

import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz

LINK_THRESHOLD = 0.80


@dataclass
class OpenTask:
    id: uuid.UUID
    title: str
    project: str | None = None
    priority: int | None = None


@dataclass
class TaskMatch:
    task_id: uuid.UUID | None = None
    task_title: str | None = None
    new_task_title: str | None = None
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return {"task_id": str(self.task_id) if self.task_id else None, "task_title": self.task_title,
                "new_task_title": self.new_task_title, "confidence": round(self.confidence, 2)}


def similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100


def match_task(proposal: dict | None, tasks: list[OpenTask], title: str, quote: str) -> TaskMatch:
    if not proposal:
        return TaskMatch()
    by_id = {str(t.id): t for t in tasks}
    wanted = (proposal.get("new_task_title") or "").strip()
    conf = float(proposal.get("confidence") or 0.0)
    cand = by_id.get(str(proposal.get("task_id") or ""))
    probes = [x for x in (wanted, title) if x]
    if cand is not None and max((similarity(cand.title, p) for p in probes), default=0.0) >= LINK_THRESHOLD:
        return TaskMatch(cand.id, cand.title, None, conf)
    if wanted:  # model-named work item: link an existing task that is close enough, else propose a new one
        best = max(tasks, key=lambda t: similarity(t.title, wanted), default=None)
        if best is not None and similarity(best.title, wanted) >= LINK_THRESHOLD:
            return TaskMatch(best.id, best.title, None, conf)
        return TaskMatch(None, None, wanted[:160], conf)
    return TaskMatch()
