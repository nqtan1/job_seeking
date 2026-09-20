import io
import json
import pytest
from fastapi.testclient import TestClient
from main import app
import workers.background as bg


@pytest.fixture(autouse=True)
def test_db(tmp_path):
    # Create a fresh temporary database path for each test
    temp_db = tmp_path / "test_cross_tenant_isolation.db"
    old_manager = bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = bg.BackgroundJobManager(db_path=str(temp_db))
    yield bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = old_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_applications_cross_tenant_isolation(client):
    """
    Verify that tenant B cannot read, list, update, delete, or upload files
    to applications belonging to tenant A.
    """
    # 1. Tenant A creates an application
    payload = {
        "company_name": "Google",
        "source": "linkedin",
        "applied_date": "2026-09-15",
        "status": "applied",
        "jd_summary": "Software Engineer role on Gemini team",
    }
    response = client.post(
        "/api/applications",
        json=payload,
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 201
    app_data = response.json()
    application_id = app_data["application_id"]

    # 2. Tenant B attempts to read Tenant A's application -> 404
    response_get = client.get(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_get.status_code == 404

    # 3. Tenant B attempts to list applications -> should get 0 results
    response_list = client.get(
        "/api/applications",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_list.status_code == 200
    assert len(response_list.json()) == 0

    # 4. Tenant B attempts to update Tenant A's application -> 404
    update_payload = {
        "company_name": "Alphabet",
        "source": "linkedin",
        "applied_date": "2026-09-15",
        "status": "interview",
    }
    response_put = client.put(
        f"/api/applications/{application_id}",
        json=update_payload,
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_put.status_code == 404

    # 5. Tenant B attempts to upload file to Tenant A's application -> 404
    file_content = b"Candidate resume contents"
    response_upload = client.post(
        f"/api/applications/{application_id}/upload",
        data={"file_type": "cv"},
        files={"file": ("resume.pdf", io.BytesIO(file_content), "application/pdf")},
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_upload.status_code == 404

    # 6. Tenant B attempts to delete Tenant A's application -> 404
    response_delete = client.delete(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_delete.status_code == 404


def test_cv_candidates_cross_tenant_isolation(client, tmp_path):
    """
    Verify that tenant B cannot list or access files of candidates belonging to tenant A.
    """
    # Create a mock file path on disk
    mock_cv_file = tmp_path / "jane_doe_cv.pdf"
    mock_cv_file.write_bytes(b"Jane Doe CV contents")

    # Save a candidate belonging to tenant-a in DB
    candidate_id = bg._BACKGROUND_JOB_MANAGER.save_candidate(
        tenant_id="test-tenant-1",
        name="Jane Doe",
        email="jane@example.com",
        phone="555-0199",
        extracted_data_json='{}',
        file_path=str(mock_cv_file)
    )

    # 1. Tenant B attempts to list candidates -> 0 results
    response_list = client.get(
        "/api/cv/candidates",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_list.status_code == 200
    assert len(response_list.json()["candidates"]) == 0

    # 2. Tenant B attempts to fetch candidate's CV file -> 404
    response_file = client.get(
        f"/api/cv/candidates/{candidate_id}/file",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response_file.status_code == 404


def test_hr_background_jobs_cross_tenant_isolation(client):
    """
    Verify that tenant B cannot query the status/result of a background ranking job belonging to tenant A.
    """
    def dummy_func():
        return {"message": "success"}

    # Create a background job belonging to test-tenant-1
    job_id = bg._BACKGROUND_JOB_MANAGER.submit(
        tenant_id="test-tenant-1",
        job_type="hr_ranking",
        func=dummy_func
    )

    # 1. Tenant B attempts to query job status/result -> 403 Forbidden
    response = client.get(
        f"/api/hr/jobs/{job_id}",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this job"
