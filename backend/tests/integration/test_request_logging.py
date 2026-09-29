"""P1-05: request ids, the access log, and the guarantee that no query string, body, or
personal data reaches the logs."""

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from recruitai.core.errors import Forbidden
from recruitai.core.logging import bind_context
from recruitai.main import create_app

SECRET_QUERY = "email=jane@example.com&token=SECRET123&cv=John-Smith-CV"
SECRET_BODY = "TOP-SECRET-BODY-jane@example.com"


class Payload(BaseModel):
    text: str
    n: int


def _build() -> FastAPI:
    app = create_app()

    @app.get("/t/ok")
    async def _ok() -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/t/bind-async")
    async def _bind_async() -> dict[str, str]:
        bind_context(org_id="org-A", user_id="user-A")
        return {"ok": "1"}

    @app.get("/t/bind-sync")
    def _bind_sync() -> dict[str, str]:  # runs in the threadpool
        bind_context(org_id="org-S", user_id="user-S")
        return {"ok": "1"}

    @app.get("/t/forbidden")
    async def _forbidden() -> None:
        raise Forbidden()

    @app.get("/t/boom")
    async def _boom() -> None:
        raise ValueError("secret detail jane@example.com")

    @app.get("/t/boom-bound")
    async def _boom_bound() -> None:
        bind_context(org_id="org-B", user_id="user-B")
        raise ValueError("secret")

    @app.post("/t/payload")
    async def _payload(p: Payload) -> None:
        return None

    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=_build(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


def _lines(capsys) -> list[dict]:
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _access(lines: list[dict]) -> list[dict]:
    return [r for r in lines if r.get("event") == "http_request"]


# ------------------------------------------------------------------ request id and access log


async def test_request_ids_are_generated_unique_honoured_when_valid_and_replaced_when_not(
    client, capsys
):
    ids = {(await client.get("/t/ok")).headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5 and all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids)
    capsys.readouterr()

    resp = await client.get("/t/ok", headers={"X-Request-Id": "trace-abc.123_X"})
    assert resp.headers["x-request-id"] == "trace-abc.123_X"
    assert _access(_lines(capsys))[0]["request_id"] == "trace-abc.123_X"

    for bad in ("a" * 65, "has space", "<script>", "a/b", "x;y", ""):
        resp = await client.get("/t/ok", headers={"X-Request-Id": bad})
        assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"]), bad


async def test_one_access_line_per_request_with_fields_and_the_final_status(
    client, capsys
):
    resp = await client.get("/t/ok")
    lines = _access(_lines(capsys))
    assert len(lines) == 1
    line = lines[0]
    assert (line["method"], line["path"], line["status"], line["logger"]) == (
        "GET",
        "/t/ok",
        200,
        "recruitai.access",
    )
    assert (
        line["duration_ms"] >= 0 and line["request_id"] == resp.headers["x-request-id"]
    )

    cases = [
        ("GET", "/nope", {}, 404),
        ("POST", "/health", {}, 405),
        ("GET", "/t/forbidden", {}, 403),
        ("POST", "/t/payload", {"json": {"text": "x"}}, 422),
        ("GET", "/t/boom", {}, 500),
    ]
    for method, path, kwargs, status in cases:
        await client.request(method, path, **kwargs)
        assert [line["status"] for line in _access(_lines(capsys))] == [status], path


async def test_nothing_private_ever_reaches_the_logs(client, capsys):
    await client.get(f"/t/ok?{SECRET_QUERY}")
    await client.get(f"/t/boom?{SECRET_QUERY}")
    await client.get(f"/nope?{SECRET_QUERY}")
    await client.post(
        "/t/payload", json={"text": SECRET_BODY, "n": "not-an-int"}
    )  # 422
    await client.post(
        "/t/payload",
        content=SECRET_BODY.encode(),
        headers={"content-type": "text/plain"},
    )
    await client.get("/users/jane@example.com/cv")
    await client.get(
        "/t/ok",
        headers={"Authorization": "Bearer abc.def.ghi", "Cookie": "sid=SECRET-COOKIE"},
    )

    out = capsys.readouterr().out
    for leaked in (
        "jane@example.com", "SECRET123", "John-Smith-CV", "email=", "token=", "?",
        "TOP-SECRET", "abc.def.ghi", "SECRET-COOKIE", "secret detail",
    ):  # fmt: skip
        assert leaked not in out, leaked
    assert '"path": "/t/ok"' in out and "/users/[email]/cv" in out


# ------------------------------------------------------------------ correlation


async def test_ids_bound_in_async_and_sync_routes_reach_the_access_line_without_mixing(
    client, capsys
):
    await client.get("/t/bind-async")
    line = _access(_lines(capsys))[0]
    assert (line["org_id"], line["user_id"]) == ("org-A", "user-A")
    await client.get("/t/bind-sync")  # runs in the threadpool
    line = _access(_lines(capsys))[0]
    assert (line["org_id"], line["user_id"]) == ("org-S", "user-S")

    async def hit(n: int) -> None:
        await client.get(f"/t/ok?n={n}", headers={"X-Request-Id": f"req-{n}"})

    await asyncio.gather(*(hit(n) for n in range(40)))
    lines = _access(_lines(capsys))
    assert sorted(line["request_id"] for line in lines) == sorted(
        f"req-{n}" for n in range(40)
    )
    assert all(
        "org_id" not in line for line in lines
    )  # nothing leaked between requests


async def test_every_problem_body_carries_the_same_request_id_as_the_header(client):
    for method, path, kwargs in [
        ("GET", "/nope", {}),
        ("POST", "/health", {}),
        ("GET", "/t/forbidden", {}),
        ("POST", "/t/payload", {"json": {"text": "x"}}),
        ("GET", "/t/boom", {}),
    ]:
        resp = await client.request(method, path, **kwargs)
        assert resp.headers["content-type"].startswith("application/problem+json")
        assert resp.json()["request_id"] == resp.headers["x-request-id"], path


async def test_unhandled_error_is_traceable_keeps_bound_ids_and_leaks_nothing(
    client, capsys
):
    resp = await client.get("/t/boom-bound", headers={"X-Request-Id": "trace-500"})
    lines = _lines(capsys)

    assert resp.status_code == 500 and resp.headers["x-request-id"] == "trace-500"
    error_line = next(r for r in lines if r["logger"] == "recruitai.errors")
    assert (error_line["request_id"], error_line["org_id"], error_line["user_id"]) == (
        "trace-500",
        "org-B",
        "user-B",
    )
    assert (
        error_line["exc_type"] == "ValueError"
        and error_line["exc_frames"]
        and error_line["severity"] == "ERROR"
    )


# ------------------------------------------------------------------ the real server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_a_real_uvicorn_process_prints_only_json_and_no_query_string():
    """The order of logging configuration vs. uvicorn's own setup matters; only a real
    server proves the access log (which prints full URLs) is really off."""
    port = _free_port()
    env = {**os.environ, "ENV": "local", "LOG_LEVEL": "INFO"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "recruitai.main:app", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            pytest.fail("server did not start")
        httpx.get(f"http://127.0.0.1:{port}/health?{SECRET_QUERY}", timeout=5)
        httpx.get(f"http://127.0.0.1:{port}/nope?{SECRET_QUERY}", timeout=5)
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=20)

    lines = [line for line in out.splitlines() if line.strip()]
    assert lines, "the server printed nothing"
    parsed = [json.loads(line) for line in lines]  # every single line must be JSON
    for leaked in (
        "jane@example.com",
        "SECRET123",
        "John-Smith-CV",
        "token=",
        "email=",
    ):
        assert leaked not in out
    access = _access(parsed)
    assert {"/health", "/nope"} <= {r["path"] for r in access}
    assert not any(
        "HTTP/1.1" in r.get("message", "") for r in parsed
    )  # uvicorn's own access log is off
