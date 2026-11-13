"""Tag assignment order (PRD 4.8): keyword rules, exact/alias match, LLM-chosen ids, then new-tag suggestions."""

import re
import uuid
from dataclasses import dataclass, field

TAG_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(:[a-z0-9][a-z0-9_-]*)?$")
APPLY_THRESHOLD = 0.50


@dataclass
class TagInfo:
    id: uuid.UUID
    name: str
    aliases: list[str] = field(default_factory=list)
    archived: bool = False
    merged_into_id: uuid.UUID | None = None


@dataclass
class RuleInfo:
    phrase: str
    target_type: str  # tag | category
    target_id: uuid.UUID


@dataclass
class TagCandidate:
    tag_id: uuid.UUID | None
    name: str
    source: str  # rule | alias | ai
    reason: str | None
    confidence: float
    new: bool = False

    @property
    def applied(self) -> bool:
        return self.confidence >= APPLY_THRESHOLD and (self.tag_id is not None or self.new)

    def as_dict(self) -> dict:
        return {"tag_id": str(self.tag_id) if self.tag_id else None, "name": self.name, "source": self.source, "reason": self.reason,
                "confidence": round(self.confidence, 2), "new": self.new, "applied": self.applied}


def phrase_in(text: str, phrase: str) -> bool:
    """Whole-word, case-insensitive: 'art' must not match 'party' (AC-047)."""
    p = phrase.strip()
    return bool(p) and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text, re.IGNORECASE) is not None


def normalise_tag_name(name: str) -> str | None:
    n = re.sub(r"[\s_]+", "-", name.strip().lower().lstrip("#"))
    n = re.sub(r"[^a-z0-9:_-]", "", n).strip("-")
    return n if TAG_NAME_RE.match(n) and len(n) <= 48 else None


def match_tags(haystack: str, rules: list[RuleInfo], tags: list[TagInfo], proposals: list[dict]) -> tuple[list[TagCandidate], uuid.UUID | None]:
    by_id = {t.id: t for t in tags}
    by_name: dict[str, TagInfo] = {}
    for t in tags:
        by_name[t.name.lower()] = t
        for a in t.aliases:
            by_name.setdefault(a.lower(), t)

    def resolve(t: TagInfo | None) -> TagInfo | None:
        """Archived tags are never candidates; a merged tag resolves to its target."""
        if t is None:
            return None
        if t.merged_into_id and t.merged_into_id in by_id:
            return resolve(by_id[t.merged_into_id])
        return None if t.archived else t

    out: dict[str, TagCandidate] = {}
    category_override: uuid.UUID | None = None

    for r in rules:  # 1. keyword rules win regardless of the model
        if not phrase_in(haystack, r.phrase):
            continue
        if r.target_type == "category":
            category_override = category_override or r.target_id
        elif (t := resolve(by_id.get(r.target_id))) is not None:
            out[str(t.id)] = TagCandidate(t.id, t.name, "rule", r.phrase, 1.0)

    for p in proposals:  # 2/3. exact or alias match, then the model's own ids
        conf = float(p.get("confidence", 0.8))
        reason = (p.get("reason") or None)
        name = (p.get("name") or "").strip()
        tag: TagInfo | None = None
        source = "ai"
        if p.get("tag_id"):
            try:
                tag = by_id.get(uuid.UUID(str(p["tag_id"])))
            except ValueError:
                tag = None
        if tag is None and name:
            tag = by_name.get(name.lower().lstrip("#"))
            if tag is not None:
                source = "alias" if tag.name.lower() != name.lower().lstrip("#") else "ai"
        if tag is not None:
            if (resolved := resolve(tag)) is not None and str(resolved.id) not in out:
                out[str(resolved.id)] = TagCandidate(resolved.id, resolved.name, source, reason, conf)
            continue
        norm = normalise_tag_name(name)  # 4. a concept with no match becomes a suggestion
        if norm and f"new:{norm}" not in out and not any(c.name == norm for c in out.values()):
            known = by_name.get(norm)
            if known is not None and resolve(known) is None:
                continue  # archived with no merge target: do not resurrect it
            out[f"new:{norm}"] = TagCandidate(None, norm, "ai", reason, conf, new=True)
    return list(out.values()), category_override
