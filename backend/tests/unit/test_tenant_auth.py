import pytest
from fastapi import HTTPException

from core.auth import get_tenant_registry, resolve_tenant_context


def test_default_context_when_registry_not_configured(monkeypatch):
    monkeypatch.delenv("TENANT_API_KEYS_JSON", raising=False)
    get_tenant_registry.cache_clear()

    with pytest.raises(HTTPException) as exc:
        resolve_tenant_context()

    assert exc.value.status_code == 401
    assert "not configured" in exc.value.detail


def test_resolve_tenant_context_missing_credentials(monkeypatch):
    monkeypatch.setenv("TENANT_API_KEYS_JSON", '{"tenant-a": ["key-a"]}')
    get_tenant_registry.cache_clear()

    with pytest.raises(HTTPException) as exc_missing_both:
        resolve_tenant_context()
    assert exc_missing_both.value.status_code == 401

    with pytest.raises(HTTPException) as exc_missing_key:
        resolve_tenant_context(tenant_id="tenant-a")
    assert exc_missing_key.value.status_code == 401

    with pytest.raises(HTTPException) as exc_missing_id:
        resolve_tenant_context(api_key="key-a")
    assert exc_missing_id.value.status_code == 401


def test_resolve_tenant_context_rejects_unknown_tenant(monkeypatch):
    monkeypatch.setenv("TENANT_API_KEYS_JSON", '{"tenant-a": ["key-a"]}')
    get_tenant_registry.cache_clear()

    with pytest.raises(HTTPException) as exc:
        resolve_tenant_context("unknown-tenant", "key-a")

    assert exc.value.status_code == 403
    assert exc.value.detail == "Unknown tenant"


def test_resolve_tenant_context_validates_api_key(monkeypatch):
    monkeypatch.setenv("TENANT_API_KEYS_JSON", '{"tenant-a": ["key-a"]}')
    get_tenant_registry.cache_clear()

    context = resolve_tenant_context("tenant-a", "key-a")

    assert context.tenant_id == "tenant-a"
    assert context.is_authenticated is True


def test_resolve_tenant_context_rejects_invalid_api_key(monkeypatch):
    monkeypatch.setenv("TENANT_API_KEYS_JSON", '{"tenant-a": ["key-a"]}')
    get_tenant_registry.cache_clear()

    with pytest.raises(HTTPException) as exc:
        resolve_tenant_context("tenant-a", "wrong-key")

    assert exc.value.status_code == 403