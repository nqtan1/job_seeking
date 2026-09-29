from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from domain.cv.schema import CVInformation, PersonalInfo
from domain.jobs.schema import JobPosition, CompanyInfo, Badges, Profile, AboutCompany, Modalities, SourceMeta
from domain.motivation_letter.schema import MotivationLetter, MotivationLetterMetadata


def _cv():
    return CVInformation(personal_info=PersonalInfo(name="Jane Doe", phone="0600000000")).model_dump()


def _job():
    return JobPosition(
        title="Backend Engineer",
        company=CompanyInfo(name="Acme"),
        badges=Badges(),
        about_company=AboutCompany(summary=""),
        profile=Profile(),
        modalities=Modalities(),
        source_meta=SourceMeta(),
    ).model_dump()


def _build_client(tmp_path):
    from main import app
    import api.motivation_letter as ml_route

    fake_agent = MagicMock()
    fake_agent.generate_letter.return_value = MotivationLetter(
        content="Dear Hiring Manager, ...",
        metadata=MotivationLetterMetadata(
            job_type="startup",
            language="en",
            tone="professional",
            format="txt",
            generated_at=datetime.now(),
            system_prompt_used="test",
            llm_model="test",
        ),
    )
    ml_route.agent = fake_agent
    ml_route.service.db_base_dir = tmp_path

    return TestClient(app)


def test_generate_temp_pdf_url_includes_api_key_and_is_fetchable(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/api/motivation-letter/generate-temp-pdf",
        json={
            "cv_info": _cv(),
            "job_info": _job(),
            "job_type": "startup",
            "language": "en",
            "tone": "professional",
            "return_format": "txt",
        },
        headers={"X-Tenant-Id": "test-tenant-1", "X-API-Key": "key-1"},
    )
    assert response.status_code == 200
    data = response.json()

    assert "tenant_id=test-tenant-1" in data["pdf_url"]
    assert "api_key=key-1" in data["pdf_url"]

    # The url must be fetchable using ONLY its own query params, with no headers at
    # all — this is exactly how an <iframe src="..."> consumes it in the browser.
    file_response = client.get(data["pdf_url"], headers={"X-Skip-Tenant-Inject": "1"})
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "application/pdf"
