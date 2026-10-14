"""ADR 0024: absolute lifetime and step-up come from the token's auth_time (boundaries)."""

import time
from unittest.mock import patch

import pytest

from recruitai.config import Settings
from recruitai.core import auth
from recruitai.core.errors import ReauthRequired

S = Settings.model_construct(
    session_absolute_days=7, stepup_max_age_seconds=300, auth_time_leeway_seconds=30
)


async def _verify(age_s: int, max_age_s: int | None = None):
    claims = {"uid": "u", "email": "a@b.c", "auth_time": int(time.time()) - age_s}
    with patch.object(auth.firebase_auth, "verify_id_token", return_value=claims):
        return await auth._verify(
            None,
            S,
            "Bearer t",
            check_revoked=True,
            max_age_s=max_age_s,  # type: ignore[arg-type]
        )


async def test_absolute_lifetime():
    assert (await _verify(7 * 86400 - 60)).firebase_uid == "u"
    with pytest.raises(ReauthRequired) as e:
        await _verify(7 * 86400 + 120)
    assert e.value.code == "reauth_required" and e.value.extensions == {"recent": False}


async def test_step_up_4_min_ok_6_min_rejected():
    assert (await _verify(240, max_age_s=300)).firebase_uid == "u"
    with pytest.raises(ReauthRequired) as e:
        await _verify(360, max_age_s=300)
    assert e.value.extensions == {"recent": True}


async def test_a_future_auth_time_is_not_trusted():
    with pytest.raises(ReauthRequired):
        await _verify(-3600)
