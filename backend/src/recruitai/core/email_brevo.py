"""Brevo (ex-Sendinblue) transactional email over its REST API (ARCHITECTURE.md §9)."""

from typing import Any

import httpx

from recruitai.core.email import render
from recruitai.core.errors import UpstreamUnavailable

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailSender:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        sender_email: str,
        sender_name: str,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._sender = {"email": sender_email, "name": sender_name}

    async def send(self, to: str, template: str, context: dict[str, Any]) -> None:
        subject, body = render(template, context)
        try:
            response = await self._client.post(
                BREVO_URL,
                headers={"api-key": self._api_key, "accept": "application/json"},
                json={
                    "sender": self._sender,
                    "to": [{"email": to}],
                    "subject": subject,
                    "textContent": body,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Fixed message: the SDK text can contain the recipient's address.
            raise UpstreamUnavailable(
                "The email service is unavailable.", code="email_unavailable"
            ) from exc
