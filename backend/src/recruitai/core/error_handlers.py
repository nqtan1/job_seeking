"""One place that turns every failure into RFC 9457 problem+json.

Nothing here may echo exception text, validation input, or provider messages: the body is
built only from developer-authored ``AppError.detail``, the HTTP status phrase, and the
field location + error *type* of validation failures. Unhandled errors are logged (the
formatter strips the exception message) and answered with a generic 500. Every response
carries the request id (body ``request_id`` + ``X-Request-Id`` header) so a user-reported
error can be traced in the logs.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from recruitai.core.errors import AppError, ValidationFailed
from recruitai.core.logging import use_context
from recruitai.core.middleware import (
    LOG_CONTEXT_SCOPE_KEY,
    REQUEST_ID_HEADER,
    REQUEST_ID_SCOPE_KEY,
)

PROBLEM_JSON = "application/problem+json"
logger = logging.getLogger("recruitai.errors")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_failed",
    429: "rate_limited",
}


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except (
        ValueError
    ):  # non-standard status code: never let the error handler itself fail
        return "Error"


def _problem(
    request: Request,
    status: int,
    code: str,
    detail: str,
    *,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _phrase(status),
        "status": status,
        "detail": detail,
        "code": code,
    }
    if errors:
        body["errors"] = errors
    out_headers = dict(headers or {})
    # Read from the ASGI scope, not a contextvar: unhandled-error responses are built by the
    # outermost middleware, after the request context has already been reset.
    request_id = request.scope.get(REQUEST_ID_SCOPE_KEY)
    if request_id:
        body["request_id"] = request_id
        out_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_JSON, headers=out_headers
    )


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem(
        request,
        int(exc.status_code),
        exc.code,
        exc.detail,
        errors=exc.errors,
        headers=exc.headers,
    )


async def _request_validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only location + error type. pydantic's `msg` carries custom-validator ValueError text
    # and `input` echoes what the client sent: neither is ever returned.
    errors = [
        {"loc": ".".join(str(part) for part in err["loc"]), "type": str(err["type"])}
        for err in exc.errors()
    ]
    default = ValidationFailed()
    return _problem(
        request, int(default.status_code), default.code, default.detail, errors=errors
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    # `exc.detail` is intentionally ignored: it may have been written with internals in it.
    code = _STATUS_CODES.get(status, "http_error")
    headers = dict(exc.headers) if exc.headers else None
    return _problem(request, status, code, _phrase(status), headers=headers)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Runs in the outermost middleware, after the request context was reset: re-enter it so
    # this (most important) log line carries request_id / org_id / user_id.
    with use_context(request.scope.get(LOG_CONTEXT_SCOPE_KEY) or {}):
        logger.error("unhandled exception (%s)", type(exc).__name__, exc_info=exc)
    generic = AppError()
    return _problem(
        request, int(generic.status_code), generic.code, generic.default_detail
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _request_validation)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(Exception, _unhandled)
