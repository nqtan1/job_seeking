import asyncio
import json
import logging
import uuid
from datetime import datetime

import psycopg.errors
import pytest
from pydantic import ValidationError

from recruitai.config import Settings
from recruitai.core.logging import (
    JsonFormatter,
    bind_context,
    configure_logging,
    get_context,
    request_context,
    scrub,
)

FMT = JsonFormatter()


def render(
    msg="hello", *args, level=logging.INFO, exc: BaseException | None = None, **extra
) -> dict:
    exc_info = (type(exc), exc, exc.__traceback__) if exc is not None else None
    record = logging.LogRecord("t.logger", level, __file__, 1, msg, args, exc_info)
    record.__dict__.update(extra)
    line = FMT.format(record)
    assert "\n" not in line  # exactly one line per record
    return json.loads(line)


# ------------------------------------------------------------------ shape and context


def test_record_shape_and_correlation_fields():
    out = render("hello %s", "world", level=logging.WARNING)
    assert out["message"] == "hello world" and (out["severity"], out["logger"]) == (
        "WARNING",
        "t.logger",
    )
    assert datetime.fromisoformat(out["timestamp"]).utcoffset().total_seconds() == 0
    assert not (
        {"request_id", "org_id", "user_id", "task_id"} & set(out)
    )  # absent when unbound

    uid = uuid.uuid4()
    with request_context(request_id="req-1"):
        bind_context(org_id=uid, user_id="u-1", task_id=7)
        bind_context(org_id=None)  # None is skipped, not stored
        out = render()
        with pytest.raises(ValueError):
            bind_context(email="a@b.c")  # only correlation fields can be bound
    assert (out["request_id"], out["org_id"], out["user_id"], out["task_id"]) == (
        "req-1",
        str(uid),
        "u-1",
        "7",
    )
    assert "request_id" not in render()  # cleared when the context exits


async def test_contexts_are_isolated_between_tasks_and_visible_across_threads():
    async def one(n: int) -> str:
        with request_context(request_id=f"r{n}"):
            await asyncio.sleep(0.01 * (n % 3))
            return get_context()["request_id"]

    assert await asyncio.gather(*(one(n) for n in range(30))) == [
        f"r{n}" for n in range(30)
    ]

    with request_context(request_id="r"):
        await asyncio.to_thread(
            bind_context, org_id="org-from-thread"
        )  # a threadpool copy of the context
        assert get_context()["org_id"] == "org-from-thread"


# ------------------------------------------------------------------ extras and scrubbing


def test_extras_scalars_kept_objects_dropped_sensitive_keys_redacted_and_no_spoofing():
    out = render(
        event="http_request", status=200, duration_ms=1.5, cached=True, note=None
    )
    assert (out["event"], out["status"], out["duration_ms"], out["cached"], out["note"]) == (
        "http_request", 200, 1.5, True, None,
    )  # fmt: skip
    dropped = render(a={"a": 1}, b=["x"], c=object(), d=("t",), e=b"bytes")
    assert not ({"a", "b", "c", "d", "e"} & set(dropped))
    for key in (
        "email",
        "Email",
        "body",
        "query_string",
        "cv",
        "token",
        "Authorization",
        "password",
    ):
        out = render(**{key: "sensitive value"})
        assert out[key] == "[redacted]" and "sensitive value" not in json.dumps(out), (
            key
        )
    assert render(detail="from jane@example.com")["detail"] == "from [email]"
    spoof = render(
        request_id="spoofed", org_id="spoofed", severity="CRITICAL", message="forged"
    )
    assert "request_id" not in spoof and "org_id" not in spoof
    assert (spoof["severity"], spoof["message"]) == ("INFO", "hello")


def test_scrub_removes_emails_jwts_and_bearer_tokens_but_leaves_normal_text():
    cases = {
        "mail jane.doe+cv@sub.example.co.uk now": "mail [email] now",
        "a@b.io and c@d.org": "[email] and [email]",
        "Authorization: Bearer abc.DEF-123_456": "Authorization: [bearer]",
        "jwt eyJhbGciOiJub25lIn0.eyJ1aWQiOiIxIn0.sig end": "jwt [jwt] end",
        "2026-09-29 12:00:00 at 100% cpu": "2026-09-29 12:00:00 at 100% cpu",
    }
    for raw, expected in cases.items():
        assert scrub(raw) == expected, raw
    assert "@" not in render("user %s failed", "jane@example.com")["message"]


# ------------------------------------------------------------------ exceptions


def _raise(msg: str):
    try:
        raise ValueError(msg)
    except ValueError as e:
        return e


def test_exception_message_is_never_logged_but_type_chain_sqlstate_and_frames_are():
    out = render("boom", exc=_raise("Key (email)=(jane@example.com) already exists"))
    assert "jane@example.com" not in json.dumps(
        out
    ) and "already exists" not in json.dumps(out)
    assert out["exc_type"] == "ValueError" and out["exc_chain"] == ["ValueError"]
    assert any(
        f.endswith(" _raise") and "test_logging.py:" in f for f in out["exc_frames"]
    )

    try:
        try:
            raise KeyError("inner secret cv text")
        except KeyError as inner:
            raise RuntimeError("outer secret") from inner
    except RuntimeError as e:
        chained = render("x", exc=e)
    assert chained["exc_chain"] == [
        "RuntimeError",
        "KeyError",
    ] and "secret" not in json.dumps(chained)

    db = render(
        "db", exc=psycopg.errors.UniqueViolation("Key (email)=(a@b.c) already exists.")
    )
    assert (db["exc_sqlstate"], db["exc_type"]) == (
        "23505",
        "UniqueViolation",
    ) and "a@b.c" not in json.dumps(db)

    def deep(n: int):
        if n == 0:
            raise RuntimeError("x")
        deep(n - 1)

    try:
        deep(100)
    except RuntimeError as e:
        assert len(render("x", exc=e)["exc_frames"]) == 30  # capped


# ------------------------------------------------------------------ robustness


def test_formatting_never_raises_and_cannot_be_used_to_forge_lines():
    class Bad:
        def __str__(self):
            raise RuntimeError("nope")

    assert render("%s %s", 1)["message"] == "[log formatting error]"
    assert render("%s", Bad())["message"] == "[log formatting error]"
    forged = render('user input\n{"severity":"CRITICAL","message":"forged"}\r\n"')
    assert (
        forged["severity"] == "INFO" and "forged" in forged["message"]
    )  # just escaped text, one line
    assert render("CV de Éloïse — 日本語")["message"] == "CV de Éloïse — 日本語"


# ------------------------------------------------------------------ configure_logging


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    yield root
    root.handlers[:], root.level = saved[0], saved[1]


def test_configure_is_idempotent_writes_json_to_stdout_and_filters_by_level(
    clean_root, capsys
):
    for _ in range(3):
        configure_logging("WARNING")
    assert (
        len([h for h in clean_root.handlers if getattr(h, "_recruitai_owned", False)])
        == 1
    )

    logging.getLogger("m").info("dropped")  # below WARNING
    logging.getLogger("m").warning("kept", extra={"event": "x"})

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["event"] == "x"


def test_url_printing_libraries_and_uvicorn_access_log_stay_quiet(clean_root, capsys):
    configure_logging("DEBUG")

    for name in ("httpx", "httpcore", "urllib3", "sqlalchemy.engine", "google.auth"):
        logging.getLogger(name).info(
            "HTTP Request: GET https://x.test/?key=SECRET-KEY-123"
        )
        assert logging.getLogger(name).level == logging.WARNING, name
    logging.getLogger("uvicorn.access").info('GET /health?token=SECRET HTTP/1.1" 200')
    logging.getLogger("uvicorn.error").info("Started server process")

    out = capsys.readouterr().out
    assert "SECRET" not in out
    lines = out.strip().splitlines()
    assert (
        len(lines) == 1 and json.loads(lines[0])["message"] == "Started server process"
    )


def test_log_level_setting(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/x_test")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert Settings(_env_file=None).log_level == "INFO"
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert Settings(_env_file=None).log_level == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
