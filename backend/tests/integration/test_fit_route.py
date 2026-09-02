from datetime import datetime
from unittest.mock import MagicMock, patch

from agents.agent_config import AgentConfig
from cv.schema import CVInformation, PersonalInfo, Experience, RawSkill
from fastapi.testclient import TestClient
from fit.schema import FitCheck, FitAnalysisResponse, FitAnalysisRequest, Recommendation
from jobs.schema import JobPosition


class FakeFitAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def analyze_fit(self, *args, **kwargs):
        return FitCheck(
            is_fit=True,
            fit_score=87,
            recommendation=Recommendation.GO,
            strengths=["Strong Python background"],
            gaps=["No direct domain experience"],
            reasons=["Core skills match", "Good seniority alignment"],
            key_missing_requirements=["French C1"],
            confidence=0.91,
            summary="Strong overall fit.",
        )


def _build_client():
    with patch("agents.base_agents.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value = MagicMock()

        from main import app
        import fit.route as fit_route

        fit_route.agent = FakeFitAgent(
            AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )
        return TestClient(app)


def test_fit_analyze_endpoint_returns_fit_check():
    client = _build_client()

    request = FitAnalysisRequest(
        candidate_cv=CVInformation(
            personal_info=PersonalInfo(name="John Doe", email="john@example.com", phone="+33612345678"),
            experiences=[Experience(job_title="ML Engineer", company="Example Corp", description="Built ML systems")],
            skills=[RawSkill(name="Python")],
        ),
        job_information=JobPosition(
            job_title="AI Engineer",
            company="Startup XYZ",
            location="Paris",
            contract_type="CDI",
        ),
        company_type="startup",
        recruiter_attend={"must_have": ["Python"]},
    )

    response = client.post("/api/fit/analyze", json=request.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Fit analysis successful"
    assert data["fit_check"]["fit_score"] == 87
    assert data["fit_check"]["recommendation"] == "go"
    assert data["company_type"] == "startup"


def test_fit_formats_endpoint_lists_company_types():
    client = _build_client()

    response = client.get("/api/fit/formats")

    assert response.status_code == 200
    data = response.json()
    assert "startup" in data["company_types"]
    assert data["supported_output"] == "FitCheck"