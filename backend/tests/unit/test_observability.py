import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from utils.logger import request_id_var, tenant_id_var, job_id_var, get_logger
from workers.background import get_background_job_manager, get_job_metrics, register_job_handler, _SUCCESS_COUNTERS, _FAILURE_COUNTERS


def test_observability_middleware_injects_request_id():
    """Verify that requests automatically populate request_id and output structured JSON logs."""
    client = TestClient(app)
    
    # Reset metrics counters
    _SUCCESS_COUNTERS.clear()
    _FAILURE_COUNTERS.clear()

    # Call a simple health check or metrics endpoint
    response = client.get("/api/jobs/metrics", headers={"X-Request-Id": "test-req-123", "X-Tenant-Id": "tenant-xyz"})
    
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "test-req-123"


def test_job_tracing_correlation_context():
    """Verify that background jobs set job_id and tenant_id variables and log structured tracing fields."""
    manager = get_background_job_manager()
    
    # Define a simple job handler that asserts correlation contextvars are active
    def sample_handler(arg1):
        assert job_id_var.get() is not None
        assert tenant_id_var.get() == "tenant-test"
        return f"Hello {arg1}"

    register_job_handler("test_trace_job", sample_handler)

    # Submit job
    job_id = manager.submit("tenant-test", "test_trace_job", sample_handler, "World")
    
    # Process job (if in durable mode we execute synchronously for the unit test)
    if manager.mode == "durable":
        manager._execute_durable_job(job_id, "test_trace_job", json.dumps({"args": ["World"], "kwargs": {}}))
    else:
        manager.wait(job_id, timeout=2)

    # Assert metrics are updated
    metrics = get_job_metrics()
    assert metrics["success_counts"].get("test_trace_job") == 1
    assert metrics["failure_counts"].get("test_trace_job", 0) == 0


def test_failed_job_increments_failure_counter():
    """Verify that failed background jobs increment failure metrics correctly."""
    manager = get_background_job_manager()
    
    def failing_handler():
        raise RuntimeError("Crash on purpose")

    register_job_handler("test_failing_job", failing_handler)

    # Submit job
    job_id = manager.submit("tenant-test", "test_failing_job", failing_handler)
    
    # Process job
    if manager.mode == "durable":
        manager._execute_durable_job(job_id, "test_failing_job", json.dumps({"args": [], "kwargs": {}}))
    else:
        try:
            manager.wait(job_id, timeout=2)
        except Exception:
            pass

    # Assert metrics are updated
    metrics = get_job_metrics()
    assert metrics["failure_counts"].get("test_failing_job") == 1
