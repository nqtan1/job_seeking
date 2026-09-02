from workers.background import BackgroundJobManager, BackgroundJobStatus


def test_background_job_manager_tracks_successful_job():
    manager = BackgroundJobManager(max_workers=1)

    job_id = manager.submit("tenant-a", "demo_job", lambda value: {"result": value + 1}, 1)
    result = manager.wait(job_id, timeout=5)
    record = manager.get(job_id)

    assert result == {"result": 2}
    assert record is not None
    assert record.status == BackgroundJobStatus.COMPLETED
    assert record.result == {"result": 2}


def test_background_job_manager_tracks_failed_job():
    manager = BackgroundJobManager(max_workers=1)

    def explode():
        raise RuntimeError("boom")

    job_id = manager.submit("tenant-a", "demo_job", explode)

    try:
        manager.wait(job_id, timeout=5)
    except RuntimeError:
        pass

    record = manager.get(job_id)
    assert record is not None
    assert record.status == BackgroundJobStatus.FAILED
    assert record.error == "boom"