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

# Fake LLM provider config so AgentConfig() construction doesn't blow up in CI,
# where there's no real GCP project/Qwen endpoint. Individual tests that need
# other values still override these via monkeypatch.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-api-key")
os.environ.setdefault("QWEN_BASE_URL", "http://localhost:8000/v1")
os.environ.setdefault("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
os.environ.setdefault("QWEN_API_KEY", "test-qwen-api-key")


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


@pytest.fixture(autouse=True)
def reset_module_level_agent_singletons():
    """
    api/{jobs,cv,motivation_letter}.py lazily cache their LLM agent in a
    module-level `agent` global on first use, and some tests overwrite it
    with a fake/mock. Without a reset, whichever test runs first "wins" for
    the rest of the session, and other tests silently talk to that stale
    agent instead of the real class their patches target.
    """
    import api.jobs as jobs_route
    import api.cv as cv_route
    import api.motivation_letter as ml_route

    yield

    jobs_route.agent = None
    cv_route.agent = None
    ml_route.agent = None
