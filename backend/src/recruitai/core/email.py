"""Transactional email (ARCHITECTURE.md §9): a protocol, a recording fake for tests, and the
selection function. The real sender is ``core/email_brevo.py``. Services take an
``EmailSender`` as an argument (like ``Storage`` and ``LLMGateway``), never import Brevo.

The ``to`` address is personal data: it is never logged, and a failure raises a fixed message.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from recruitai.config import Settings

# {template: {language: (subject, text body)}}. ``{placeholders}`` are filled from the context;
# the recipient's language is ``context["language"]`` (their account setting, English if absent).
# One language per message: never a bilingual one.
TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "inactivity_warning": {
        "en": (
            "Your RecruitAI account will be deleted in {days_left} days",
            (
                "Hello,\n\nYou have not signed in for a long time. If you do nothing, your "
                "RecruitAI account and all its data will be permanently deleted on {delete_on}. "
                "To keep it, just sign in before that date.\n"
            ),
        ),
        "fr": (
            "Votre compte RecruitAI sera supprimé dans {days_left} jours",
            (
                "Bonjour,\n\nVous ne vous êtes pas connecté depuis longtemps. Sans action de votre "
                "part, votre compte RecruitAI et toutes ses données seront définitivement "
                "supprimés le {delete_on}. Pour le conserver, connectez-vous avant cette date.\n"
            ),
        ),
        "vi": (
            "Tài khoản RecruitAI của bạn sẽ bị xóa sau {days_left} ngày",
            (
                "Xin chào,\n\nBạn đã lâu không đăng nhập. Nếu không làm gì, tài khoản RecruitAI "
                "và toàn bộ dữ liệu của bạn sẽ bị xóa vĩnh viễn vào ngày {delete_on}. "
                "Để giữ lại, chỉ cần đăng nhập trước ngày đó.\n"
            ),
        ),
    },
    "radar_inactivity_notice": {
        "en": (
            "Your RecruitAI radars will pause on {pause_on}",
            (
                "Hello,\n\nYou have not signed in for a while. To protect your data, your job "
                "radars will pause automatically on {pause_on}. Sign in before that date to keep "
                "them running, or resume them later from the Radar page.\n"
            ),
        ),
        "fr": (
            "Vos radars RecruitAI seront mis en pause le {pause_on}",
            (
                "Bonjour,\n\nVous ne vous êtes pas connecté depuis un moment. Pour protéger vos "
                "données, vos radars seront mis en pause automatiquement le {pause_on}. Connectez-"
                "vous avant cette date pour les garder actifs, ou reprenez-les plus tard depuis "
                "la page Radar.\n"
            ),
        ),
        "vi": (
            "Các radar RecruitAI của bạn sẽ tạm dừng vào ngày {pause_on}",
            (
                "Xin chào,\n\nBạn đã một thời gian không đăng nhập. Để bảo vệ dữ liệu, các radar "
                "việc làm của bạn sẽ tự động tạm dừng vào ngày {pause_on}. Hãy đăng nhập trước "
                "ngày đó để giữ chúng hoạt động, hoặc tiếp tục sau từ trang Radar.\n"
            ),
        ),
    },
    "radar_paused_failures": {
        "en": (
            "A RecruitAI radar was paused",
            (
                'Hello,\n\nYour radar "{name}" failed several days in a row, so it was paused. '
                "Open the Radar page to check it and resume it.\n"
            ),
        ),
        "fr": (
            "Un radar RecruitAI a été mis en pause",
            (
                "Bonjour,\n\nVotre radar « {name} » a échoué plusieurs jours de suite et a été "
                "mis en pause. Ouvrez la page Radar pour le vérifier et le reprendre.\n"
            ),
        ),
        "vi": (
            "Một radar RecruitAI đã bị tạm dừng",
            (
                'Xin chào,\n\nRadar "{name}" của bạn đã lỗi nhiều ngày liên tiếp nên đã bị tạm '
                "dừng. Hãy mở trang Radar để kiểm tra và tiếp tục.\n"
            ),
        ),
    },
    "application_reminders": {
        "en": (
            "RecruitAI: {count} to follow up",
            (
                "Hello,\n\nHere is what needs your attention today:\n\n{lines}\n\n"
                "Open RecruitAI to prepare or draft a follow-up. To stop these emails, turn "
                "them off in Settings.\n"
            ),
        ),
        "fr": (
            "RecruitAI : {count} à suivre",
            (
                "Bonjour,\n\nVoici ce qui demande votre attention aujourd'hui :\n\n{lines}\n\n"
                "Ouvrez RecruitAI pour vous préparer ou rédiger une relance. Pour ne plus "
                "recevoir ces e-mails, désactivez-les dans les Paramètres.\n"
            ),
        ),
        "vi": (
            "RecruitAI: {count} việc cần theo dõi",
            (
                "Xin chào,\n\nHôm nay có những việc cần bạn chú ý:\n\n{lines}\n\n"
                "Hãy mở RecruitAI để chuẩn bị hoặc soạn thư theo dõi. Để ngừng nhận các email "
                "này, hãy tắt trong phần Cài đặt.\n"
            ),
        ),
    },
}


def render(template: str, context: dict[str, Any]) -> tuple[str, str]:
    """``(subject, body)`` in ``context["language"]``. An unknown template or a missing
    placeholder is a programming error, so it raises ``KeyError`` (it must fail in tests, not
    be sent half-filled)."""
    subject, body = TEMPLATES[template][context.get("language") or "en"]
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
