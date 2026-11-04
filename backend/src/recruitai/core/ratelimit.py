"""Per-user rate limits (handbook §7), keyed by the verified Firebase uid, never client input.

A sliding window kept in memory, per instance: with N API instances a user gets up to N times
the limit. That bounds a runaway client or script; the DB-backed daily AI quota
(``ai/usage.py``) stays the real cost control. Unauthenticated floods are not limited here
(no trusted client IP behind Hosting + Cloud Run); that belongs to Cloud Run's max instances.
The window itself lives in ``core/throttle.py`` so the auth dependency can use it too.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from recruitai.core.auth import CurrentUser, get_current_user
from recruitai.core.errors import RateLimited
from recruitai.core.throttle import hit


def rate_limit(
    name: str, *, limit: int, per_s: float = 60.0
) -> Callable[..., Awaitable[None]]:
    async def dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> None:
        retry_after = hit(name, user.firebase_uid, limit=limit, per_s=per_s)
        if retry_after is not None:
            raise RateLimited(headers={"Retry-After": str(retry_after)})

    return dependency


limit_ai = rate_limit("ai", limit=20)  # every AI route also costs a model call
limit_sensitive = rate_limit("sensitive", limit=5)  # export, delete account


def limit_public(name: str, *, limit: int, per_s: float = 60.0) -> Callable[[], None]:
    """For unauthenticated routes: one *global* window per route. There is no trusted client IP
    behind Hosting + Cloud Run, so this only bounds total abuse, per instance."""

    def dependency() -> None:
        if hit("public", name, limit=limit, per_s=per_s) is not None:
            raise RateLimited(headers={"Retry-After": str(int(per_s))})

    return dependency
