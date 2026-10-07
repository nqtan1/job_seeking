"""Transactional email (ARCHITECTURE.md §9): a protocol, a recording fake for tests, and the
selection function. The real sender is ``core/email_brevo.py``. Services take an
``EmailSender`` as an argument (like ``Storage`` and ``LLMGateway``), never import Brevo.

The ``to`` address is personal data: it is never logged, and a failure raises a fixed message.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from recruitai.config import Settings

# subject, text body. ``{placeholders}`` are filled from the context. Bilingual: the account has
# no language setting yet, and a warning that is not understood is no warning.
TEMPLATES: dict[str, tuple[str, str]] = {
    "inactivity_warning": (
        (
            "Your RecruitAI account will be deleted in {days_left} days / "
            "Votre compte RecruitAI sera supprimé dans {days_left} jours"
        ),
        (
            "Hello,\n\nYou have not signed in for a long time. If you do nothing, your "
            "RecruitAI account and all its data will be permanently deleted on {delete_on}. "
            "To keep it, just sign in before that date.\n\n"
            "Bonjour,\n\nVous ne vous êtes pas connecté depuis longtemps. Sans action de votre "
            "part, votre compte RecruitAI et toutes ses données seront définitivement "
            "supprimés le {delete_on}. Pour le conserver, connectez-vous avant cette date.\n"
        ),
    ),
    "application_reminders": (
        ("RecruitAI: {count} to follow up / à suivre"),
        (
            "Hello,\n\nHere is what needs your attention today:\n\n{lines}\n\n"
            "Open RecruitAI to prepare or draft a follow-up. To stop these emails, turn "
            "them off in Settings.\n\n"
            "Bonjour,\n\nVoici ce qui demande votre attention aujourd'hui (détails "
            "ci-dessus). Ouvrez RecruitAI pour vous préparer ou rédiger une relance. Pour "
            "ne plus recevoir ces e-mails, désactivez-les dans les Paramètres.\n"
        ),
    ),
}


def render(template: str, context: dict[str, Any]) -> tuple[str, str]:
    """``(subject, body)``. An unknown template or a missing placeholder is a programming
    error, so it raises ``KeyError`` (it must fail in tests, not be sent half-filled)."""
    subject, body = TEMPLATES[template]
    return subject.format(**context), body.format(**context)


class EmailSender(Protocol):
    async def send(self, to: str, template: str, context: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SentEmail:
    to: str
    template: str
    context: dict[str, Any]


@dataclass
class FakeEmailSender:
    """Test double: records what would have been sent. Renders the template too, so a bad
    template or context fails in tests exactly as it would in production."""

    sent: list[SentEmail] = field(default_factory=list)

    async def send(self, to: str, template: str, context: dict[str, Any]) -> None:
        render(template, context)
        self.sent.append(SentEmail(to=to, template=template, context=context))


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "brevo":
        import httpx

        from recruitai.core.email_brevo import BrevoEmailSender

        return BrevoEmailSender(
            httpx.AsyncClient(timeout=15),
            api_key=settings.brevo_api_key or "",
            sender_email=settings.email_sender_address,
            sender_name=settings.email_sender_name,
        )
    return FakeEmailSender()
