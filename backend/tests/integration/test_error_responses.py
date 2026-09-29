"""P1-04: every failure is problem+json, and nothing internal ever reaches the client."""

import logging

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator

from recruitai.core.errors import (
    AppError,
    Forbidden,
    NotFound,
    UpstreamUnavailable,
    ValidationFailed,
)
from recruitai.main import create_app

SECRET = "secret detail /etc/passwd postgres://user:pw@db"


class Body(BaseModel):
    email: str
    age: int

    @field_validator("email")
    @classmethod
    def _no(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError(SECRET)  # a custom validator message must never be echoed
        return v


def _build() -> FastAPI:
    app = create_app()

    @app.get("/t/not-found")
    async def _nf() -> None:
        raise NotFound("Document not found")

    @app.get("/t/not-found-code")
    def _nfc() -> None:  # sync route path too
        raise NotFound(code="document_not_found")

    @app.get("/t/forbidden")
    async def _fb() -> None:
        raise Forbidden()

    @app.get("/t/validation")
    async def _vf() -> None:
        raise ValidationFailed(errors=[{"loc": "body.cv", "type": "too_large"}])

    @app.get("/t/upstream")
    async def _up() -> None:
        raise UpstreamUnavailable(retry_after_s=30)

    @app.get("/t/app-error")
    async def _ae() -> None:
        raise AppError()

    @app.get("/t/value-error")
    async def _ve() -> None:
        raise ValueError(SECRET)

    @app.get("/t/runtime-error-sync")
    def _rs() -> None:
        raise RuntimeError(SECRET)

    @app.get("/t/http-exception")
    async def _he() -> None:
        raise HTTPException(status_code=400, detail=SECRET)

    @app.get("/t/http-exception-headers")
    async def _hh() -> None:
        raise HTTPException(
            status_code=401, detail=SECRET, headers={"WWW-Authenticate": "Bearer"}
        )

    @app.get("/t/http-exception-odd-status")
    async def _odd() -> None:
        raise HTTPException(status_code=499, detail=SECRET)

    async def _dep() -> None:
        raise NotFound("from a dependency")

    @app.get("/t/dependency")
    async def _dp(_: None = Depends(_dep)) -> None:
        return None

    @app.get("/t/query")
    async def _q(limit: int = Query(...)) -> None:
        return None

    @app.post("/t/body")
    async def _b(body: Body) -> None:
        return None

    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=_build(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


def _assert_problem(resp: httpx.Response, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == status and body["code"] == code
    assert body["type"] == "about:blank"
    assert isinstance(body["title"], str) and isinstance(body["detail"], str)
    return body


async def test_app_errors_map_to_their_status_and_stable_code(client):
    body = _assert_problem(await client.get("/t/not-found"), 404, "not_found")
    assert body["detail"] == "Document not found" and body["title"] == "Not Found"
    _assert_problem(
        await client.get("/t/not-found-code"), 404, "document_not_found"
    )  # sync route
    _assert_problem(await client.get("/t/forbidden"), 403, "forbidden")
    _assert_problem(
        await client.get("/t/dependency"), 404, "not_found"
    )  # raised in a dependency
    _assert_problem(await client.get("/t/app-error"), 500, "internal_error")
    body = _assert_problem(await client.get("/t/validation"), 422, "validation_failed")
    assert body["errors"] == [{"loc": "body.cv", "type": "too_large"}]
    resp = await client.get("/t/upstream")
    _assert_problem(resp, 503, "upstream_unavailable")
    assert resp.headers["retry-after"] == "30"


@pytest.mark.parametrize("path", ["/t/value-error", "/t/runtime-error-sync"])
async def test_unhandled_exception_is_a_generic_500_that_never_leaks(
    client, path, caplog
):
    with caplog.at_level(logging.ERROR, logger="recruitai.errors"):
        resp = await client.get(path)

    body = _assert_problem(resp, 500, "internal_error")
    for leaked in (
        "secret detail",
        "passwd",
        "postgres://",
        "ValueError",
        "RuntimeError",
        "Traceback",
        "File ",
    ):
        assert leaked not in resp.text, leaked
    assert body["detail"] == AppError.default_detail
    record = next(
        r for r in caplog.records if r.name == "recruitai.errors"
    )  # but it IS logged
    assert record.exc_info is not None and record.exc_info[0] in (
        ValueError,
        RuntimeError,
    )


async def test_http_exceptions_never_echo_detail_keep_headers_and_survive_odd_statuses(
    client,
):
    body = _assert_problem(await client.get("/t/http-exception"), 400, "bad_request")
    assert body["detail"] == "Bad Request"

    resp = await client.get("/t/http-exception-headers")
    _assert_problem(resp, 401, "unauthorized")
    assert resp.headers["www-authenticate"] == "Bearer"

    resp = await client.get(
        "/t/http-exception-odd-status"
    )  # 499 is not in http.HTTPStatus
    _assert_problem(resp, 499, "http_error")
    assert "secret" not in resp.text


async def test_unknown_route_and_wrong_method_are_problems(client):
    _assert_problem(await client.get("/nope"), 404, "not_found")
    resp = await client.post("/health")
    _assert_problem(resp, 405, "method_not_allowed")
    assert "GET" in resp.headers["allow"]


async def test_validation_errors_report_location_and_type_only(client):
    resp = await client.get("/t/query", params={"limit": "abc-not-a-number"})
    assert _assert_problem(resp, 422, "validation_failed")["errors"] == [
        {"loc": "query.limit", "type": "int_parsing"}
    ]
    assert "abc-not-a-number" not in resp.text  # client input is not echoed

    resp = await client.post("/t/body", json={"email": "a@b.c"})
    assert _assert_problem(resp, 422, "validation_failed")["errors"] == [
        {"loc": "body.age", "type": "missing"}
    ]

    resp = await client.post(
        "/t/body", json={"email": "no-at-sign", "age": 3}
    )  # custom validator raises
    assert _assert_problem(resp, 422, "validation_failed")["errors"] == [
        {"loc": "body.email", "type": "value_error"}
    ]
    for leaked in ("secret", "passwd", "no-at-sign"):
        assert leaked not in resp.text

    resp = await client.post(
        "/t/body", content=b"{not json", headers={"content-type": "application/json"}
    )
    _assert_problem(resp, 422, "validation_failed")
    assert "not json" not in resp.text
