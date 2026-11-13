"""One place to ask for the current instant, so analytics tests can pin "now" (today is provisional, PRD D-07)."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
