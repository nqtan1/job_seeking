"""The sliding window behind every per-user limit, kept in memory per instance (so N instances
give a user up to N times the limit): it bounds a runaway client or script, while the DB-backed
daily AI quotas (``ai/usage.py``) stay the real cost control. No imports from ``auth``: the
auth dependency itself calls it."""

import time
from collections import defaultdict, deque

_MAX_KEYS = 10_000
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def hit(name: str, key: str, *, limit: int, per_s: float = 60.0) -> int | None:
    """Count one request. Returns ``None`` if allowed, else the seconds to wait."""
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:  # drop idle keys so the dict cannot grow forever
        for k in [k for k, q in _hits.items() if not q or q[-1] <= now - per_s]:
            del _hits[k]
    window = _hits[(name, key)]
    while window and window[0] <= now - per_s:
        window.popleft()
    if len(window) >= limit:
        return max(1, int(window[0] + per_s - now) + 1)
    window.append(now)
    return None
