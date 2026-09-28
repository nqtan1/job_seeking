from fastapi.testclient import TestClient


def test_health_returns_ok(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    from recruitai.main import create_app

    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
