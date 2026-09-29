import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app

@pytest.fixture(autouse=True)
def test_db(tmp_path):
    import workers.background as bg
    # Create a fresh temporary database path for each test
    temp_db = tmp_path / "test_background_jobs.db"
    old_manager = bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = bg.BackgroundJobManager(db_path=str(temp_db))
    yield bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = old_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_crud_applications(client):
    # 1. Create Application
    payload = {
        "company_name": "Google",
        "source": "linkedin",
        "applied_date": "2026-09-15",
        "status": "applied",
        "jd_summary": "Software Engineer role on Gemini team",
        "recruiter_response": None,
        "cv_file": None,
        "cover_letter_file": None
    }
    
    response = client.post(
        "/api/applications",
        json=payload,
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["company_name"] == "Google"
    assert data["status"] == "applied"
    assert data["tenant_id"] == "test-tenant-1"
    assert "application_id" in data
    
    application_id = data["application_id"]
    
    # 2. Get Application
    response = client.get(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 200
    assert response.json()["company_name"] == "Google"
    
    # 3. List Applications (filtered and sorted)
    response = client.get(
        "/api/applications",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 200
    apps = response.json()
    assert len(apps) == 1
    assert apps[0]["application_id"] == application_id
    
    # 4. Update Application
    update_payload = {
        "company_name": "Alphabet Inc.",
        "source": "referral",
        "applied_date": "2026-09-16",
        "status": "interview",
        "jd_summary": "Updated summary",
        "recruiter_response": "First round scheduled",
        "cv_file": "/path/to/cv",
        "cover_letter_file": "/path/to/cl"
    }
    response = client.put(
        f"/api/applications/{application_id}",
        json=update_payload,
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["company_name"] == "Alphabet Inc."
    assert updated_data["source"] == "referral"
    assert updated_data["status"] == "interview"
    assert updated_data["recruiter_response"] == "First round scheduled"
    
    # 5. Multi-Tenant isolation test (another tenant should not see this application)
    response = client.get(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response.status_code == 404
    
    response = client.get(
        "/api/applications",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 0

    # 6. Delete Application
    response = client.delete(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 204
    
    # Get deleted should return 404
    response = client.get(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 404


def test_file_upload_and_serving(client):
    # 1. Create Application first
    payload = {
        "company_name": "Apple",
        "source": "company_site",
        "applied_date": "2026-09-14",
        "status": "to_apply"
    }
    response = client.post(
        "/api/applications",
        json=payload,
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 201
    application_id = response.json()["application_id"]

    # 2. Upload CV file
    file_content = b"Mock resume content PDF"
    response = client.post(
        f"/api/applications/{application_id}/upload",
        data={"file_type": "cv"},
        files={"file": ("my_resume.pdf", io.BytesIO(file_content), "application/pdf")},
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "my_resume.pdf" in data["cv_file"]
    cv_url = data["cv_file"]

    # 3. Serve/Get CV File
    filename = cv_url.split("/")[-1]
    response = client.get(
        f"/api/applications/files/{filename}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 200
    assert response.content == file_content

    # 4. Multi-tenant access block
    response = client.get(
        f"/api/applications/files/{filename}",
        headers={"X-Tenant-ID": "test-tenant-2"}
    )
    assert response.status_code == 403

    # 5. Delete Application and verify local files are deleted
    response = client.delete(
        f"/api/applications/{application_id}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 204

    # File should be deleted on disk, so server returns 404 for that file now
    response = client.get(
        f"/api/applications/files/{filename}",
        headers={"X-Tenant-ID": "test-tenant-1"}
    )
    assert response.status_code == 404
