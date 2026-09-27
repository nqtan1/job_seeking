from workers.background import BackgroundJobManager


def test_get_job_is_scoped_to_tenant(tmp_path):
    manager = BackgroundJobManager(db_path=str(tmp_path / "test_jobs.db"))

    job_id = manager.save_job(
        tenant_id="tenant-a",
        job_title="Backend Engineer",
        company="Acme",
        extracted_data_json="{}",
    )

    assert manager.get_job(job_id, tenant_id="tenant-a") is not None
    assert manager.get_job(job_id, tenant_id="tenant-b") is None


def test_get_fit_analysis_is_scoped_to_tenant(tmp_path):
    manager = BackgroundJobManager(db_path=str(tmp_path / "test_fit.db"))

    analysis_id = manager.save_fit_analysis(
        tenant_id="tenant-a",
        candidate_id="cand-1",
        job_id="job-1",
        fit_score=80,
        fit_data_json="{}",
    )

    assert manager.get_fit_analysis(analysis_id, tenant_id="tenant-a") is not None
    assert manager.get_fit_analysis(analysis_id, tenant_id="tenant-b") is None
