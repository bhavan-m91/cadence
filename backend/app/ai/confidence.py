"""Confidence = min(llm overall, time, category) x penalties from code (PRD 6.8), with three bands."""

PENALTIES = {
    "quote_unverified": 0.60,
    "boundary_inferred": 0.90,
    "meridiem_inferred": 0.90,
    "approximate": 0.95,
    "unplaced": 0.85,
}
UNRESOLVED_CAP = 0.49
HIGH, MEDIUM = 0.80, 0.50


def final_confidence(overall: float, time: float, category: float, flags: set[str], unresolved: bool) -> float:
    c = min(overall, time, category)
    for f, mult in PENALTIES.items():
        if f in flags:
            c *= mult
    if unresolved:
        c = min(c, UNRESOLVED_CAP)
    return round(max(0.0, min(1.0, c)), 2)


def band(c: float) -> str:
    return "high" if c >= HIGH else "medium" if c >= MEDIUM else "low"
