"""Cheap wins on every response: big JSON is gzipped, the ping is public and empty."""

from fastapi.testclient import TestClient

from recruitai.main import create_app


def test_large_json_is_gzipped_and_ping_is_public_and_empty():
    client = TestClient(create_app())
    big = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert big.headers["content-encoding"] == "gzip"
    ping = client.get("/api/ping")
    assert ping.status_code == 204 and ping.content == b""
