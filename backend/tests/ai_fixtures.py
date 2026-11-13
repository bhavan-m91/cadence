"""Canned model output for the PRD's worked example (section 6.5), built against a real user's category and tag ids."""

TEXT = ("Started my day at around 9:30. Spent an hour researching how to implement the new AI feature. After that, worked on Product A until 1 PM, "
        "mainly debugging the API and fixing some database issues. Had lunch from 1 to 2. In the afternoon, attended a meeting for about 45 minutes "
        "and then worked on Product B until 6.")


def tod(h, m=0, mer=None):
    return {"hour": h, "minute": m, "meridiem": mer}


def prd_response(p, *, variant: str = "a") -> dict:
    deep, meals, meet = p.cats["Deep work"], p.cats["Meals & chores"], p.cats["Meetings"]
    tag = lambda n: {"tag_id": p.tags[n], "name": n, "reason": n, "confidence": 0.9}  # noqa: E731

    def act(i, title, quote, cat, ref, tags=(), conf=(0.9, 0.9, 0.9)):
        return {"temp_id": f"a{i}", "order": i, "title": title, "description": None, "source_quote": quote, "category_id": cat, "time_ref": ref, "tags": list(tags),
                "task": None, "location_type": None, "confidence": dict(zip(("overall", "time", "category"), conf, strict=True)), "flags": []}

    acts = [
        act(1, "Research new AI feature", "Started my day at around 9:30. Spent an hour researching how to implement the new AI feature", deep,
            {"kind": "range", "start": tod(9, 30), "duration_minutes": 60, "approximate": True, "quote": "around 9:30 ... an hour"}, [tag("research")], (0.9, 0.85, 0.8)),
        act(2, "Product A: API debugging and database fixes", "After that, worked on Product A until 1 PM, mainly debugging the API and fixing some database issues", deep,
            {"kind": "range", "start_anchor": "previous_end", "end": tod(1, 0, "pm"), "quote": "After that ... until 1 PM"},
            [tag("bug"), {"tag_id": None, "name": "product-a", "new": True, "reason": "Product A", "confidence": 0.95}]),
        act(3, "Lunch", "Had lunch from 1 to 2", meals, {"kind": "range", "start": tod(1), "end": tod(2), "quote": "from 1 to 2"}, conf=(0.95, 0.9, 0.95)),
        act(4, "Meeting", "In the afternoon, attended a meeting for about 45 minutes", meet,
            {"kind": "vague", "duration_minutes": 45, "approximate": True, "window": {"label": "afternoon"}, "quote": "In the afternoon ... about 45 minutes"}, [tag("meetings")], (0.75, 0.5, 0.9)),
        act(5, "Product B work", "and then worked on Product B until 6", deep, {"kind": "range", "start_anchor": "previous_end", "end": tod(6), "quote": "and then ... until 6"},
            [{"tag_id": None, "name": "product-b", "new": True, "reason": "Product B", "confidence": 0.95}], (0.8, 0.7, 0.9)),
    ]
    if variant == "b":  # a second run that proposes slightly different titles
        for a in acts:
            a["title"] = a["title"] + " (v2)"
    return {"schema_version": "1", "entry_summary": "Research, Product A debugging, lunch, a meeting and Product B", "activities": acts}
