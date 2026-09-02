import io
import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from agents.agent_config import AgentConfig
from cv.schema import CVInformation, Experience, PersonalInfo, RawSkill
from hr.schema import HRBatchRankingRequest, HRCandidateInput
from jobs.schema import JobPosition
from workers.background import get_background_job_manager
from core.auth import get_tenant_registry


class FakeFitAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def analyze_fit(self, candidate_cv, job_information, company_type, output_schema=None, **kwargs):
        fit_score = 92 if candidate_cv.personal_info.name == "Alice Martin" else 78
        return output_schema(
            is_fit=True,
            fit_score=fit_score,
            recommendation="go" if fit_score >= 80 else "maybe",
            strengths=[f"Strong match for {job_information.job_title}"],
            gaps=["No direct domain experience"],
            reasons=["Core skills align", "Reasonable seniority match"],
            key_missing_requirements=["French C1"],
            confidence=0.9,
            summary="Strong fit overall.",
        )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-credentials.json")
    monkeypatch.setenv("TENANT_API_KEYS_JSON", '{"tenant-a": ["tenant-key-a"]}')
    get_tenant_registry.cache_clear()

    with patch("agents.base_agents.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value = MagicMock()

        from main import app
        import hr.route as hr_route

        hr_route.fit_agent = FakeFitAgent(
            AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )
        get_background_job_manager()
        return TestClient(app)


def _build_hr_request() -> HRBatchRankingRequest:
    return HRBatchRankingRequest(
        job_information=JobPosition(
            job_title="AI Engineer",
            company="Startup XYZ",
            location="Paris",
            contract_type="CDI",
        ),
        company_type="startup",
        shortlist_size=1,
        candidates=[
            HRCandidateInput(
                candidate_id="cand-1",
                candidate_cv=CVInformation(
                    personal_info=PersonalInfo(name="Alice Martin", email="alice@example.com", phone="+33611111111"),
                    experiences=[Experience(job_title="ML Engineer", company="Example Corp", description="Built ML systems")],
                    skills=[RawSkill(name="Python")],
                ),
            ),
            HRCandidateInput(
                candidate_id="cand-2",
                candidate_cv=CVInformation(
                    personal_info=PersonalInfo(name="Bob Dupont", email="bob@example.com", phone="+33622222222"),
                    experiences=[Experience(job_title="Data Analyst", company="Example Corp", description="Built dashboards")],
                    skills=[RawSkill(name="SQL")],
                ),
            ),
        ],
    )


def test_hr_rank_requires_tenant_auth(client):
    response = client.get("/api/hr/context")
    assert response.status_code == 401


def test_hr_rank_sync_returns_ranked_candidates(client):
    request = _build_hr_request()

    response = client.post(
        "/api/hr/rank?background=false",
        json=request.model_dump(),
        headers={"X-Tenant-Id": "tenant-a", "X-API-Key": "tenant-key-a"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "HR batch ranking successful"
    assert data["tenant_id"] == "tenant-a"
    assert data["ranked_candidates"][0]["candidate_name"] == "Alice Martin"
    assert data["ranked_candidates"][0]["shortlisted"] is True
    assert data["ranked_candidates"][1]["shortlisted"] is False


def test_hr_rank_background_job_can_be_polled(client):
    request = _build_hr_request()

    response = client.post(
        "/api/hr/rank?background=true",
        json=request.model_dump(),
        headers={"X-Tenant-Id": "tenant-a", "X-API-Key": "tenant-key-a"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"

    background_manager = get_background_job_manager()
    background_manager.wait(data["job_id"], timeout=5)

    status_response = client.get(
        f"/api/hr/jobs/{data['job_id']}",
        headers={"X-Tenant-Id": "tenant-a", "X-API-Key": "tenant-key-a"},
    )

    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["result"]["message"] == "HR batch ranking successful"