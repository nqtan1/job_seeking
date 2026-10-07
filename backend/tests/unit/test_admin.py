"""core/auth.py is_admin: verified email on the allowlist, case-insensitive; nobody else."""

from recruitai.config import Settings
from recruitai.core.auth import CurrentUser, is_admin


def test_admin_needs_allowlisted_and_verified_email():
    s = Settings.model_construct(admin_emails=["Boss@Example.com"])
    ok = CurrentUser("u1", "boss@example.com", email_verified=True)
    unverified = CurrentUser("u2", "boss@example.com", email_verified=False)
    other = CurrentUser("u3", "other@example.com", email_verified=True)

    assert is_admin(ok, s)
    assert not is_admin(unverified, s)
    assert not is_admin(other, s)
    assert not is_admin(ok, Settings.model_construct(admin_emails=[]))
