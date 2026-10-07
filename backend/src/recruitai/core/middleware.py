"""Pure-ASGI request-context middleware: request id, ``X-Request-Id``, one access-log line.

Pure ASGI (not ``BaseHTTPMiddleware``) so streaming responses (SSE, later) and contextvars
behave. Logs the URL **path only**: never the query string, headers, or body.
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
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with request_context(request_id=request_id) as ctx:
            scope[LOG_CONTEXT_SCOPE_KEY] = (
                ctx  # lets the outermost error handler re-enter it
            )
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                extra: dict[str, Any] = {
                    "event": "http_request",
                    "method": scope["method"],
                    "path": scrub(scope["path"]),  # never scope["query_string"]
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
                logger.info("http_request", extra=extra)
