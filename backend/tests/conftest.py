import pytest
import asyncio 


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
