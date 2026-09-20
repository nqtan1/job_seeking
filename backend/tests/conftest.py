import os
import json
import pytest
import asyncio
from fastapi.testclient import TestClient


# Set up global environment variable for all tests
os.environ.setdefault("JOB_QUEUE_MODE", "in_memory")

os.environ.setdefault(
    "TENANT_API_KEYS_JSON",
    json.dumps({
        "test-tenant-1": ["key-1"],
        "test-tenant-2": ["key-2"],
        "test-tenant-cv": ["key-cv"],
        "different-tenant": ["key-diff"],
        "tenant-a": ["tenant-key-a"],
        "test-tenant-123": ["key-123"],
        "default": ["key-default"],
    })
)


# Monkeypatch TestClient.request to automatically inject tenant headers and API keys in tests
original_request = TestClient.request

def patched_request(self, method: str, url: str, **kwargs):
    headers = kwargs.get("headers") or {}
    normalized_headers = {k.lower(): (k, v) for k, v in headers.items()}

    # Check for bypass header
    if "x-skip-tenant-inject" in normalized_headers:
        key_to_remove = normalized_headers["x-skip-tenant-inject"][0]
        headers.pop(key_to_remove, None)
        kwargs["headers"] = headers
        return original_request(self, method, url, **kwargs)

    # Check for X-Tenant-ID / X-Tenant-Id / tenant_id
    tenant_key = None
    tenant_id = None
    for k in ["x-tenant-id", "x-tenant-id"]:
        if k in normalized_headers:
            tenant_key, tenant_id = normalized_headers[k]
            break

    # If no tenant ID is specified at all, default to "test-tenant-1"
    if not tenant_key:
        headers["X-Tenant-Id"] = "test-tenant-1"
        tenant_id = "test-tenant-1"

    # If tenant ID is present but no API key, inject the appropriate test API key
    has_api_key = any(k in normalized_headers for k in ["x-api-key", "x-api-key"])
    if not has_api_key:
        key_map = {
            "test-tenant-1": "key-1",
            "test-tenant-2": "key-2",
            "test-tenant-cv": "key-cv",
            "different-tenant": "key-diff",
            "tenant-a": "tenant-key-a",
            "test-tenant-123": "key-123",
            "default": "key-default",
        }
        headers["X-API-Key"] = key_map.get(tenant_id, "key-default")

    kwargs["headers"] = headers
    return original_request(self, method, url, **kwargs)

TestClient.request = patched_request


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def clear_tenant_registry_cache():
    """Clear the tenant registry LRU cache to prevent state leakage across tests."""
    from core.auth import get_tenant_registry
    get_tenant_registry.cache_clear()
