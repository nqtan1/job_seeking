from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from domain.cv.schema import CVInformation, Experience, PersonalInfo, RawSkill
from domain.fit.schema import FitAnalysisRequest, FitCheck, Recommendation
from domain.jobs.schema import (
    AboutCompany,
    Badges,
    CompanyInfo,
    JobPosition,
    Modalities,
    Profile,
    SourceMeta,
)
from infrastructure.agents.agent_config import AgentConfig


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
    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value = MagicMock()

        import api.fit as fit_route
        from main import app

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
            personal_info=PersonalInfo(
                name="John Doe", email="john@example.com", phone="+33612345678"
            ),
            experiences=[
                Experience(
                    job_title="ML Engineer",
                    company="Example Corp",
                    description="Built ML systems",
                )
            ],
            skills=[RawSkill(name="Python")],
        ),
        job_information=JobPosition(
            title="AI Engineer",
            company=CompanyInfo(name="Startup XYZ", type="employer"),
            badges=Badges(
                location="Paris",
                contract_type="CDI",
            ),
            about_company=AboutCompany(summary=""),
            missions=[],
            tech_stack=[],
            working_methods=[],
            profile=Profile(),
            modalities=Modalities(),
            source_meta=SourceMeta(),
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
