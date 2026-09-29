"""Structured JSON logging with request/org/user/task correlation (ARCHITECTURE.md §4.8).

Privacy rules enforced here, not left to discipline (CLAUDE.md, ADR 0014):
* the exception **message** is never logged (DB errors embed row values, e.g. emails): only
  the exception type chain, the sqlstate, and stack frames;
* emails, JWTs and ``Bearer`` tokens are scrubbed from every message and extra field;
* ``extra=`` fields must be scalars, and keys that usually hold personal data are redacted;
* only the URL *path* is ever logged (see ``core.middleware``); uvicorn's access log, which
  prints the query string, is silenced, and HTTP-client loggers that print URLs are pinned
  to WARNING.
"""

import json
import logging
import re
import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

CORRELATION_FIELDS = ("request_id", "org_id", "user_id", "task_id")

# Values stored per request in one mutable dict, so ids bound later (auth) are visible to the
# access-log line and to threadpool copies of the context.
_context: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)


@contextmanager
def request_context(**fields: object) -> Iterator[dict[str, str]]:
    ctx: dict[str, str] = {}
    token = _context.set(ctx)
    try:
        bind_context(**fields)
        yield ctx
    finally:
        _context.reset(token)


@contextmanager
def use_context(ctx: dict[str, str]) -> Iterator[None]:
    """Re-enter a request's context (for code that runs after ``request_context`` has exited,
    e.g. the outermost error handler)."""
    token = _context.set(ctx)
    try:
        yield
    finally:
        _context.reset(token)


def bind_context(**fields: object) -> None:
    """Attach correlation ids (``request_id``, ``org_id``, ``user_id``, ``task_id``)."""
    unknown = set(fields) - set(CORRELATION_FIELDS)
    if unknown:
        raise ValueError(f"not a correlation field: {sorted(unknown)}")
    ctx = _context.get()
    if ctx is None:
        ctx = {}
        _context.set(ctx)
    for key, value in fields.items():
        if value is not None:
            ctx[key] = str(value)


def get_context() -> dict[str, str]:
    return dict(_context.get() or {})


# ---------------------------------------------------------------- scrubbing

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]+")

_SENSITIVE_KEYS = frozenset(
    {
        "email", "body", "query", "query_string", "cv", "letter", "text", "content", "prompt",
        "password", "token", "authorization", "cookie", "secret", "api_key", "key", "name",
        "phone", "address",
    }
)  # fmt: skip


def scrub(text: str) -> str:
    text = _JWT.sub("[jwt]", text)
    text = _BEARER.sub("[bearer]", text)
    return _EMAIL.sub("[email]", text)


# ---------------------------------------------------------------- formatting

_STANDARD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    }
)  # fmt: skip
_MAX_FRAMES = 30


def _frames(exc: BaseException) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)[-_MAX_FRAMES:]
    return [
        f"{'/'.join(f.filename.replace(chr(92), '/').split('/')[-3:])}:{f.lineno} {f.name}"
        for f in frames
    ]


def _exception_fields(exc: BaseException) -> dict[str, Any]:
    chain: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen and len(chain) < 5:
        seen.add(id(cur))
        chain.append(type(cur).__name__)
        cur = cur.__cause__ or cur.__context__
    fields: dict[str, Any] = {
        "exc_type": type(exc).__name__,
        "exc_chain": chain,
        "exc_frames": _frames(exc),
    }
    sqlstate = getattr(exc, "sqlstate", None)
    if isinstance(sqlstate, str):
        fields["exc_sqlstate"] = sqlstate
    return fields


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001  # logging must never raise, whatever the args' __str__ does
            message = "[log formatting error]"
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": scrub(message),
        }
        payload.update(get_context())
        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_ATTRS
                or key in payload
                or key in CORRELATION_FIELDS  # extras can never spoof a correlation id
                or key.startswith("_")
            ):
                continue
            if key.lower() in _SENSITIVE_KEYS:
                payload[key] = "[redacted]"
            elif isinstance(value, str):
                payload[key] = scrub(value)
            elif value is None or isinstance(value, bool | int | float):
                payload[key] = value
            # anything else (objects, dicts, lists) is dropped: it could carry personal data
        if record.exc_info and record.exc_info[1] is not None:
            payload.update(_exception_fields(record.exc_info[1]))
        return json.dumps(
            payload, ensure_ascii=False, default=lambda _: "[unserializable]"
        )


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to whatever ``sys.stdout`` is *now* (so test capture and reloads just work)."""

    _recruitai_owned = True

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())

    @property
    def stream(self) -> Any:
        return sys.stdout

    @stream.setter
    def stream(self, _value: Any) -> None:
        return None


# Libraries that print URLs (with query strings / keys) or SQL parameters at INFO.
_QUIET_LOGGERS = (
    "httpx", "httpcore", "urllib3", "google", "google.auth", "google.api_core",
    "sqlalchemy.engine", "openai",
)  # fmt: skip


def configure_logging(level: str = "INFO") -> None:
    """Idempotent: JSON to stdout, one handler, safe library loggers."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_recruitai_owned", False):
            root.removeHandler(handler)
    root.addHandler(_StdoutHandler())
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = (
            True  # through our JSON handler (exception text is stripped there)
        )
    access = logging.getLogger(
        "uvicorn.access"
    )  # prints the full URL incl. query string
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
