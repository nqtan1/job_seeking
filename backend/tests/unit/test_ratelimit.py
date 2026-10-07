"""Per-user sliding-window limit: over the limit -> 429 + Retry-After; other users unaffected."""

import pytest

from recruitai.core.auth import CurrentUser
from recruitai.core.ratelimit import RateLimited, rate_limit


async def test_the_limit_is_per_user_and_answers_429_with_retry_after():
    check = rate_limit("unit-test", limit=2)
    ada, bob = CurrentUser("ada", "a@x.test"), CurrentUser("bob", "b@x.test")
    await check(ada)
    await check(ada)
    with pytest.raises(RateLimited) as exc:
        await check(ada)
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1
    await check(bob)  # someone else is not affected
