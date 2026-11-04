"""Pure-ASGI request-context middleware: request id, ``X-Request-Id``, one access-log line, the
basic security headers, and a hard cap on the request body (no unbounded upload held in memory).

Pure ASGI so streaming (SSE) works. Logs the URL path only, never query, headers or body.
"""

import logging
import re
import time
import uuid
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recruitai.core.logging import request_context, scrub

REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_SCOPE_KEY = "recruitai.request_id"
LOG_CONTEXT_SCOPE_KEY = "recruitai.log_context"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger("recruitai.access")

MAX_BODY_BYTES = (
    12 * 1024 * 1024
)  # the biggest upload is 10 MiB, plus multipart framing
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",  # personal data: never kept by a shared cache
}


class _TooLarge(Exception):
    pass


def _too_large_response() -> tuple[int, bytes]:
    return (
        413,
        b'{"type":"about:blank","title":"Request too large","status":413,"code":"payload_too_large"}',
    )


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_ID.fullmatch(candidate) else None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        scope[REQUEST_ID_SCOPE_KEY] = request_id
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        declared = next(
            (v for k, v in scope.get("headers", []) if k == b"content-length"), b""
        )
        received = 0
        started_response = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started_response
            started_response = (
                started_response or message["type"] == "http.response.start"
            )
            await send_with_id(message)

        with request_context(request_id=request_id) as ctx:
            scope[LOG_CONTEXT_SCOPE_KEY] = (
                ctx  # lets the outermost error handler re-enter it
            )
            try:
                if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
                    raise _TooLarge
                await self.app(scope, limited_receive, tracking_send)
            except _TooLarge:
                if not started_response:
                    status, body = _too_large_response()
                    await send_with_id(
                        {
                            "type": "http.response.start",
                            "status": status,
                            "headers": [(b"content-type", b"application/problem+json")],
                        }
                    )
                    await send_with_id({"type": "http.response.body", "body": body})
            finally:
                extra: dict[str, Any] = {
                    "event": "http_request",
                    "method": scope["method"],
                    "path": scrub(scope["path"]),  # never scope["query_string"]
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
                logger.info("http_request", extra=extra)
