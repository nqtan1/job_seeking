"""ADR 0024 signed links: valid, tampered, expired, wrong secret, wrong shape."""

from uuid import uuid4

from recruitai.modules.radar import links

SECRET = "x" * 32
ORG, USER = uuid4(), uuid4()


def _token(ttl_s=100, now=1_000.0, org=ORG):
    return links.sign(SECRET, org_id=org, user_id=USER, ttl_s=ttl_s, now=now)


def test_a_valid_link_names_one_org_and_user():
    assert links.verify(SECRET, _token(), now=1_050.0) == links.LinkClaims(ORG, USER)


def test_expired_tampered_and_foreign_links_are_rejected():
    t = _token()
    assert links.verify(SECRET, t, now=1_101.0) is None  # expired (30 days in prod)
    assert links.verify("y" * 32, t, now=1_050.0) is None  # other secret
    assert links.verify("", t, now=1_050.0) is None  # no secret never verifies
    body, sig = t.split(".")
    other_body = _token(org=uuid4()).split(".")[0]
    assert (
        links.verify(SECRET, f"{other_body}.{sig}", now=1_050.0) is None
    )  # swapped body
    for junk in ("", "abc", "a.b", t + "x", "..", f"{body}."):
        assert links.verify(SECRET, junk, now=1_050.0) is None
