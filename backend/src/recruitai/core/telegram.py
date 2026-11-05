"""The platform's Telegram bot (ADR 0036): a protocol, the HTTP client, and a recording fake for tests.
Services take a ``Telegram`` as an argument (like ``EmailSender``), never import httpx for it.

The bot token is in the URL of every request, so nothing here logs a URL, a chat id or a message, and
every failure is a fixed code."""

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from recruitai.config import Settings

API = "https://api.telegram.org"
MAX_MESSAGE = 4096  # Telegram's own limit for one message
TIMEOUT_S = 10.0
NOT_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)  # nothing left yet


class TelegramError(Exception):
    """The send or poll failed. ``blocked``: the bot was refused by the chat (HTTP 403).
    ``unknown``: the request left but no answer came (read timeout), so the message may have been
    delivered; false for a connect error or an error status, where it certainly was not."""

    def __init__(self, blocked: bool = False, unknown: bool = False) -> None:
        super().__init__("telegram_failed")
        self.blocked = blocked
        self.unknown = unknown


@dataclass(frozen=True)
class Update:
    update_id: int
    chat_id: int
    text: str


class Telegram(Protocol):
    username: str

    async def send(self, chat_id: int, text: str) -> None: ...

    async def updates(self) -> list[Update]:
        """Pending private text messages, and acknowledged: each is returned once."""
        ...


class HttpTelegram:
    def __init__(self, token: str, username: str) -> None:
        self._token = token
        self.username = username

    async def _call(self, method: str, **params: object) -> object:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                r = await client.post(f"{API}/bot{self._token}/{method}", json=params)
        except (
            httpx.HTTPError
        ) as exc:  # the exception text holds the URL, and the token
            raise TelegramError(unknown=not isinstance(exc, NOT_SENT)) from None
        if r.status_code == 403:  # bot blocked, user deactivated (a 400 proves nothing)
            raise TelegramError(blocked=True)
        if r.status_code != 200:
            raise TelegramError()
        return r.json().get("result")

    async def send(self, chat_id: int, text: str) -> None:
        await self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text[:MAX_MESSAGE],
            disable_web_page_preview=True,  # plain text: no parse_mode, so no markup injection
        )

    async def updates(self) -> list[Update]:
        raw = await self._call("getUpdates", timeout=0, limit=100)
        items = raw if isinstance(raw, list) else []
        found = [
            Update(u["update_id"], m["chat"]["id"], str(m["text"]))
            for u in items
            if isinstance(m := u.get("message"), dict)
            and m.get("chat", {}).get("type") == "private"
            and isinstance(m.get("text"), str)
        ]
        if items:  # acknowledge them all, also those we ignore, so none comes back
            await self._call(
                "getUpdates", offset=items[-1]["update_id"] + 1, limit=1, timeout=0
            )
        return found


@dataclass
class FakeTelegram:
    username: str = "recruitai_test_bot"
    sent: list[tuple[int, str]] = field(default_factory=list)
    inbox: list[Update] = field(default_factory=list)
    blocked: set[int] = field(default_factory=set)

    async def send(self, chat_id: int, text: str) -> None:
        if chat_id in self.blocked:
            raise TelegramError(blocked=True)
        self.sent.append((chat_id, text[:MAX_MESSAGE]))

    async def updates(self) -> list[Update]:
        found, self.inbox = self.inbox, []
        return found


def get_telegram(settings: Settings) -> Telegram | None:
    """None when no bot is configured: the feature says "not available" instead of failing."""
    if not settings.telegram_bot_token or not settings.telegram_bot_username:
        return None
    return HttpTelegram(settings.telegram_bot_token, settings.telegram_bot_username)
