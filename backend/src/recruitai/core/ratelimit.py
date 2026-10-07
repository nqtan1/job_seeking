"""Per-user rate limits (handbook §7), keyed by the verified Firebase uid, never client input.

A sliding window kept in memory, per instance: with N API instances a user gets up to N times
the limit. That bounds a runaway client or script; the DB-backed daily AI quota
(``ai/usage.py``) stays the real cost control. Unauthenticated floods are not limited here
(no trusted client IP behind Hosting + Cloud Run); that belongs to Cloud Run's max instances.
"""

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from recruitai.core.auth import CurrentUser, get_current_user
from recruitai.core.errors import AppError

_MAX_KEYS = 10_000
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    default_detail = "Too many requests. Please slow down and try again shortly."


def rate_limit(
    name: str, *, limit: int, per_s: float = 60.0
) -> Callable[..., Awaitable[None]]:
    async def dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> None:
        now = time.monotonic()
        if len(_hits) > _MAX_KEYS:  # drop idle users so the dict cannot grow forever
            for key in [k for k, q in _hits.items() if not q or q[-1] <= now - per_s]:
                del _hits[key]
        window = _hits[(name, user.firebase_uid)]
        while window and window[0] <= now - per_s:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(window[0] + per_s - now) + 1)
            raise RateLimited(headers={"Retry-After": str(retry_after)})
        window.append(now)

    return dependency


limit_ai = rate_limit("ai", limit=20)  # every AI route also costs a model call
limit_sensitive = rate_limit("sensitive", limit=5)  # export, delete account
