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
    assert resp.status_code == status
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == status and body["code"] == code
    assert body["type"] == "about:blank"
    assert isinstance(body["title"], str) and isinstance(body["detail"], str)
    return body


async def test_not_found(client):
    body = _assert_problem(await client.get("/t/not-found"), 404, "not_found")

    assert body["detail"] == "Document not found" and body["title"] == "Not Found"


async def test_not_found_with_specific_code_from_a_sync_route(client):
    _assert_problem(await client.get("/t/not-found-code"), 404, "document_not_found")


async def test_forbidden(client):
    _assert_problem(await client.get("/t/forbidden"), 403, "forbidden")


async def test_validation_failed_carries_field_errors(client):
    body = _assert_problem(await client.get("/t/validation"), 422, "validation_failed")

    assert body["errors"] == [{"loc": "body.cv", "type": "too_large"}]


async def test_upstream_unavailable_sets_retry_after(client):
    resp = await client.get("/t/upstream")

    _assert_problem(resp, 503, "upstream_unavailable")
    assert resp.headers["retry-after"] == "30"


async def test_app_error_raised_in_a_dependency_is_handled(client):
    _assert_problem(await client.get("/t/dependency"), 404, "not_found")


async def test_bare_app_error_is_a_generic_500(client):
    _assert_problem(await client.get("/t/app-error"), 500, "internal_error")


@pytest.mark.parametrize("path", ["/t/value-error", "/t/runtime-error-sync"])
async def test_unhandled_exception_is_a_generic_500_that_never_leaks(client, path):
    resp = await client.get(path)

    body = _assert_problem(resp, 500, "internal_error")
    assert "secret detail" not in resp.text
    for leaked in (
        "passwd",
        "postgres://",
        "ValueError",
        "RuntimeError",
        "Traceback",
        "File ",
    ):
        assert leaked not in resp.text
    assert body["detail"] == AppError.default_detail


async def test_unhandled_exception_is_logged_with_its_traceback(client, caplog):
    with caplog.at_level(logging.ERROR, logger="recruitai.errors"):
        await client.get("/t/value-error")

    record = next(r for r in caplog.records if r.name == "recruitai.errors")
    assert record.exc_info is not None and record.exc_info[0] is ValueError
    assert "ValueError" in record.getMessage()


async def test_http_exception_detail_is_never_echoed(client):
    resp = await client.get("/t/http-exception")

    body = _assert_problem(resp, 400, "bad_request")
    assert body["detail"] == "Bad Request" and "secret" not in resp.text


async def test_http_exception_headers_are_preserved(client):
    resp = await client.get("/t/http-exception-headers")

    _assert_problem(resp, 401, "unauthorized")
    assert resp.headers["www-authenticate"] == "Bearer" and "secret" not in resp.text


async def test_non_standard_http_status_does_not_break_the_handler(client):
    resp = await client.get("/t/http-exception-odd-status")

    _assert_problem(resp, 499, "http_error")
    assert "secret" not in resp.text


async def test_unknown_route_is_a_problem_404(client):
    _assert_problem(await client.get("/nope"), 404, "not_found")


async def test_wrong_method_is_a_problem_405_with_allow_header(client):
    resp = await client.post("/health")

    _assert_problem(resp, 405, "method_not_allowed")
    assert "GET" in resp.headers["allow"]


async def test_query_validation_reports_location_and_type_only(client):
    resp = await client.get("/t/query", params={"limit": "abc-not-a-number"})

    body = _assert_problem(resp, 422, "validation_failed")
    assert body["errors"] == [{"loc": "query.limit", "type": "int_parsing"}]
    assert "abc-not-a-number" not in resp.text  # the client's input is not echoed back


async def test_missing_body_field_is_reported_by_location(client):
    resp = await client.post("/t/body", json={"email": "a@b.c"})

    body = _assert_problem(resp, 422, "validation_failed")
    assert body["errors"] == [{"loc": "body.age", "type": "missing"}]


async def test_custom_validator_message_and_input_are_not_echoed(client):
    resp = await client.post("/t/body", json={"email": "no-at-sign", "age": 3})

    body = _assert_problem(resp, 422, "validation_failed")
    assert body["errors"] == [{"loc": "body.email", "type": "value_error"}]
    assert (
        "secret" not in resp.text
        and "passwd" not in resp.text
        and "no-at-sign" not in resp.text
    )


async def test_malformed_json_body_is_a_problem_422(client):
    resp = await client.post(
        "/t/body", content=b"{not json", headers={"content-type": "application/json"}
    )

    _assert_problem(resp, 422, "validation_failed")
    assert "not json" not in resp.text


async def test_health_still_works(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
