"""core/email.py + core/email_brevo.py (P2-30a): never a real network call or send."""

import httpx
import pytest

from recruitai.config import Settings
from recruitai.core.email import FakeEmailSender, get_email_sender, render
from recruitai.core.email_brevo import BREVO_URL, BrevoEmailSender
from recruitai.core.errors import UpstreamUnavailable

CTX = {"days_left": 7, "delete_on": "2028-01-01"}


async def test_the_fake_records_what_would_be_sent_and_renders_the_template():
    sender = FakeEmailSender()
    await sender.send("ada@example.test", "inactivity_warning", CTX)
    assert [(m.to, m.template, m.context) for m in sender.sent] == [
        ("ada@example.test", "inactivity_warning", CTX)
    ]
    subject, body = render("inactivity_warning", CTX)
    assert (
        "7" in subject and "2028-01-01" in body and "Bonjour" in body
    )  # both languages
    with pytest.raises(
        KeyError
    ):  # a bad template/context fails in tests, not in production
        await sender.send("a@example.test", "nope", {})
    with pytest.raises(KeyError):
        await sender.send("a@example.test", "inactivity_warning", {"days_left": 7})
    assert len(sender.sent) == 1


async def test_brevo_posts_the_rendered_email_with_the_api_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"messageId": "x"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = BrevoEmailSender(
        client, api_key="k-123", sender_email="a@b.test", sender_name="RA"
    )

    await sender.send("ada@example.test", "inactivity_warning", CTX)

    request = seen[0]
    assert str(request.url) == BREVO_URL and request.headers["api-key"] == "k-123"
    import json

    payload = json.loads(request.content)
    assert payload["to"] == [{"email": "ada@example.test"}]
    assert payload["sender"] == {"email": "a@b.test", "name": "RA"}
    assert "7 days" in payload["subject"] and "2028-01-01" in payload["textContent"]


async def test_brevo_failures_are_a_clean_error_that_never_contains_the_address():
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key for ada@example.test")

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot reach ada@example.test")

    for handler in (failing, broken):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sender = BrevoEmailSender(
            client, api_key="k", sender_email="a@b.test", sender_name="RA"
        )
        with pytest.raises(UpstreamUnavailable) as err:
            await sender.send("ada@example.test", "inactivity_warning", CTX)
        assert err.value.code == "email_unavailable" and "ada@" not in err.value.detail


def _settings(**over) -> Settings:
    base = {"env": "local", "database_url": "postgresql+psycopg://u:p@localhost/x_test",
            "firebase_project_id": "demo"}  # fmt: skip
    return Settings(_env_file=None, **{**base, **over})  # type: ignore[call-arg]


def test_the_api_key_is_required_only_when_brevo_is_selected():
    assert isinstance(
        get_email_sender(_settings()), FakeEmailSender
    )  # default: no key needed
    with pytest.raises(ValueError, match="BREVO_API_KEY"):
        _settings(email_backend="brevo")
    brevo = get_email_sender(_settings(email_backend="brevo", brevo_api_key="k"))
    assert isinstance(brevo, BrevoEmailSender)
