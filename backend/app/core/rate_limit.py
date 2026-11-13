"""In-process sliding-window rate limiter (FR-150). One API instance in V1.0; swap for a shared store if scaled out."""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def count(self, key: str, window: float) -> int:
        return len(self._prune(key, window, time.monotonic()))

    def hit(self, key: str, window: float) -> int:
        now = time.monotonic()
        q = self._prune(key, window, now)
        q.append(now)
        return len(q)

    def retry_after(self, key: str, window: float) -> int:
        now = time.monotonic()
        q = self._prune(key, window, now)
        return int(q[0] + window - now) + 1 if q else 0

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


limiter = SlidingWindowLimiter()
