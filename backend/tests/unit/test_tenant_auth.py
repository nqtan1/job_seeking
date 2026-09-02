import pytest
from fastapi import HTTPException

from core.auth import get_tenant_registry, resolve_tenant_context


def test_default_context_when_registry_not_configured(monkeypatch):
    monkeypatch.delenv("TENANT_API_KEYS_JSON", raising=False)
    get_tenant_registry.cache_clear()

    context = resolve_tenant_context()

    assert context.tenant_id == "default"
    assert context.is_authenticated is False


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