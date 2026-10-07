"""core/auth.py (P1-06): token verification only, no database access.

Note on "expired": the Auth emulator does not enforce token expiry at all (firebase_admin's
_token_gen.py takes the ``if emulated: verified_claims = payload`` branch, skipping the
``google.oauth2.id_token.verify_token`` call where exp is normally checked) — confirmed by
reading the installed library, not assumed. A genuinely expired token cannot be produced
end-to-end through the emulator, so that one case is verified by making
``firebase_auth.verify_id_token`` raise ``ExpiredIdTokenError`` directly: it proves our code
converts that exception into a 401, which is what actually matters in production, where the
real check does run.
"""

from unittest.mock import patch

import pytest
from firebase_admin import auth as firebase_auth
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import get_settings
from recruitai.core.auth import CurrentUser, get_current_user, get_firebase_app
from recruitai.core.errors import Unauthorized


@pytest.fixture(scope="session")
def firebase_app():
    return get_firebase_app(get_settings())


async def test_valid_token_resolves_current_user_and_writes_no_row(
    emulator_token, firebase_app, db_session: AsyncSession
):
    token = emulator_token("uid-auth-valid", "auth-valid@example.test")

    user = await get_current_user(firebase_app, authorization=f"Bearer {token}")

    assert user == CurrentUser(
        firebase_uid="uid-auth-valid", email="auth-valid@example.test"
    )
    count = (await db_session.execute(text("SELECT count(*) FROM users"))).scalar()
    assert count == 0


@pytest.mark.parametrize(
    "authorization",
    [None, "not-bearer-scheme abc", "Bearer ", "Bearer not-a-real-jwt-at-all"],
)
async def test_missing_malformed_or_invalid_token_is_401(firebase_app, authorization):
    with pytest.raises(Unauthorized):
        await get_current_user(firebase_app, authorization=authorization)


async def test_expired_token_is_401(firebase_app):
    with (
        patch.object(
            firebase_auth,
            "verify_id_token",
            side_effect=firebase_auth.ExpiredIdTokenError("token expired", cause=None),
        ),
        pytest.raises(Unauthorized),
    ):
        await get_current_user(firebase_app, authorization="Bearer irrelevant")
