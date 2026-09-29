"""One place that turns every failure into RFC 9457 problem+json.

Nothing here may echo exception text, validation input, or provider messages: the body is
built only from developer-authored ``AppError.detail``, the HTTP status phrase, and the
field location + error *type* of validation failures. Unhandled errors are logged (with
traceback) and answered with a generic 500.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from recruitai.core.errors import AppError, ValidationFailed

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
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_JSON, headers=headers
    )


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem(
        int(exc.status_code),
        exc.code,
        exc.detail,
        errors=exc.errors,
        headers=exc.headers,
    )


async def _request_validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only location + error type. pydantic's `msg` carries custom-validator ValueError text
    # and `input` echoes what the client sent: neither is ever returned.
    errors = [
        {"loc": ".".join(str(part) for part in err["loc"]), "type": str(err["type"])}
        for err in exc.errors()
    ]
    default = ValidationFailed()
    return _problem(
        int(default.status_code), default.code, default.detail, errors=errors
    )


async def _http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    # `exc.detail` is intentionally ignored: it may have been written with internals in it.
    code = _STATUS_CODES.get(status, "http_error")
    headers = dict(exc.headers) if exc.headers else None
    return _problem(status, code, _phrase(status), headers=headers)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled exception (%s)", type(exc).__name__, exc_info=exc)
    generic = AppError()
    return _problem(int(generic.status_code), generic.code, generic.default_detail)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _request_validation)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(Exception, _unhandled)
