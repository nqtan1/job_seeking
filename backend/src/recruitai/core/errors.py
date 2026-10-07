"""Domain error hierarchy. Services raise these; ``core.error_handlers`` turns them into
RFC 9457 ``application/problem+json``.

This module must stay free of FastAPI/Starlette (services import it; import-linter enforces
it). ``detail`` is a message the *developer authored for the user*: never pass ``str(exc)`` or
anything derived from user input, a stack trace, SQL, or a provider error.
"""

import re
from http import HTTPStatus

from pydantic import BaseModel

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class AppError(Exception):
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    default_detail: str = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if code is not None and not _CODE_RE.fullmatch(code):
            raise ValueError("error code must be snake_case ([a-z][a-z0-9_]*)")
        self.detail = detail or self.default_detail
        self.code = code or type(self).code
        self.errors = errors
        self.headers = headers or {}
        super().__init__(self.detail)


class Unauthorized(AppError):
    """Missing, malformed, invalid, expired or revoked credentials."""

    status_code = HTTPStatus.UNAUTHORIZED
    code = "unauthorized"
    default_detail = (
        "Authentication is required or the provided credentials are invalid."
    )

    def __init__(self, detail: str | None = None, *, code: str | None = None) -> None:
        super().__init__(detail, code=code, headers={"WWW-Authenticate": "Bearer"})


class NotFound(AppError):
    """Also the answer for "exists but belongs to another org": never reveal which."""

    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"
    default_detail = "The requested resource was not found."


class Forbidden(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "forbidden"
    default_detail = "You do not have permission to perform this action."


class ValidationFailed(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "validation_failed"
    default_detail = (
        "The request could not be processed because some values are invalid."
    )


class UpstreamUnavailable(AppError):
    """A dependency we call (LLM provider, France Travail, storage) is down or too slow."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "upstream_unavailable"
    default_detail = (
        "A service we depend on is temporarily unavailable. Please try again."
    )

    def __init__(
        self,
        detail: str | None = None,
        *,
        retry_after_s: int | None = None,
        code: str | None = None,
    ) -> None:
        headers = (
            {"Retry-After": str(retry_after_s)} if retry_after_s is not None else None
        )
        super().__init__(detail, code=code, headers=headers)


class ProblemDetail(BaseModel):
    """The exact shape ``core.error_handlers`` writes. Only for OpenAPI docs/codegen
    (``responses=`` on a route) — never used to build a real response body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    errors: list[dict[str, str]] | None = None
    request_id: str | None = None


def problem_responses(*errors: type[AppError]) -> dict[int | str, dict[str, object]]:
    """``responses=problem_responses(NotFound, Unauthorized)`` for a route's OpenAPI docs."""
    return {
        int(err.status_code): {
            "model": ProblemDetail,
            "description": err.default_detail,
        }
        for err in errors
    }
