import os
import sqlite3
import time
import pytest
from datetime import datetime
from workers.background import (
    BackgroundJobManager,
    BackgroundJobStatus,
    register_job_handler,
)


def sample_add_job(a: int, b: int) -> dict:
    return {"sum": a + b}


def test_durable_job_execution(monkeypatch, tmp_path):
    # Set JOB_QUEUE_MODE = "durable" explicitly for this test
    monkeypatch.setenv("JOB_QUEUE_MODE", "durable")
    
    # Register the test job type
    register_job_handler("test_addition", sample_add_job)

    # Isolated test database
    db_file = tmp_path / "test_durable_queue.db"
    manager = BackgroundJobManager(max_workers=2, db_path=str(db_file))

    try:
        # Submit a durable job
        job_id = manager.submit(
            tenant_id="test-tenant",
            job_type="test_addition",
            func=sample_add_job,  # Ignored in durable mode, matches job_type handler
            a=15,
            b=25,
        )

        # Check job has been queued in database
        record_init = manager.get(job_id)
        assert record_init is not None
        assert record_init.job_type == "test_addition"
        assert record_init.status in [BackgroundJobStatus.QUEUED, BackgroundJobStatus.RUNNING, BackgroundJobStatus.COMPLETED]

        # Wait for completion and verify results
        result = manager.wait(job_id, timeout=3.0)
        assert result == {"sum": 40}

        # Check final status in database
        record_final = manager.get(job_id)
        assert record_final is not None
        assert record_final.status == BackgroundJobStatus.COMPLETED
        assert record_final.result == {"sum": 40}
        assert record_final.completed_at is not None

    finally:
        manager.shutdown()


def test_durable_job_survives_process_kill_and_restart(monkeypatch, tmp_path):
    # Set JOB_QUEUE_MODE = "durable"
    monkeypatch.setenv("JOB_QUEUE_MODE", "durable")
    
    # Register the test job type
    register_job_handler("test_addition", sample_add_job)

    # Isolated test database
    db_file = tmp_path / "test_kill_restart.db"
    
    # --- PHASE 1: SUBMIT AND IMMEDIATELY SHUTDOWN (simulate process crash/kill) ---
    # We turn off durable mode's polling loop temporarily to ensure it doesn't run,
    # simulating a job that was enqueued right before a crash.
    monkeypatch.setenv("JOB_QUEUE_MODE", "durable_no_polling")  # Just to submit to DB and not execute
    manager_crash = BackgroundJobManager(max_workers=1, db_path=str(db_file))
    
    # Submit job manually to DB as 'queued'
    job_id = manager_crash.submit(
        tenant_id="test-tenant",
        job_type="test_addition",
        func=sample_add_job,
        a=100,
        b=200,
    )
    
    record_pre = manager_crash.get(job_id)
    assert record_pre is not None
    assert record_pre.status == BackgroundJobStatus.QUEUED
    
    # Shutdown manager (simulates killing the server process)
    manager_crash.shutdown()

    # --- PHASE 2: RESTARTS AND EXECUTES (simulate server startup) ---
    monkeypatch.setenv("JOB_QUEUE_MODE", "durable")
    manager_restart = BackgroundJobManager(max_workers=2, db_path=str(db_file))

    try:
        # Wait on the NEW manager instance to automatically pick up, process, and complete the job!
        result = manager_restart.wait(job_id, timeout=4.0)
        assert result == {"sum": 300}

        # Verify database record
        record_after = manager_restart.get(job_id)
        assert record_after is not None
        assert record_after.status == BackgroundJobStatus.COMPLETED
        assert record_after.result == {"sum": 300}

    finally:
        manager_restart.shutdown()
