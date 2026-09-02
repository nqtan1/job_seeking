import io
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.agent_config import AgentConfig
from cv.schema import CVInformation, PersonalInfo, Experience, RawSkill
from jobs.schema import CompensationInfo, JobPosition, JobRequirements
from motivation_letter.schema import MotivationLetter, MotivationLetterMetadata


class FakeResult:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self):
        return self._payload

    def model_dump_json(self, indent=None):
        return json.dumps(self._payload, ensure_ascii=False, indent=indent)


class FakeCVAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def extract_cv(self, *args, **kwargs):
        return CVInformation(
            personal_info=PersonalInfo(
                name="Clement Suto",
                email="clement_suto@example.com",
                phone="+33123456789",
                address="Paris, France",
            ),
            experiences=[
                Experience(
                    job_title="ML Engineer",
                    company="Example Corp",
                    start_date="2023",
                    end_date="Present",
                    description="Built ML systems",
                )
            ],
            skills=[RawSkill(name="Python"), RawSkill(name="Machine Learning")],
            formations=[],
        )

    def analyze_cv(self, *args, **kwargs):
        return FakeResult(
            {
                "fit_score": 0.85,
                "summary": "Strong profile",
                "strengths": ["Python", "ML"],
                "weaknesses": ["Limited production experience"],
            }
        )


class FakeJobAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def extract_job(self, *args, **kwargs):
        return JobPosition(
            job_title="Ingénieur en IA",
            company="Tech Corp France",
            location="Paris",
            contract_type="CDI",
            compensation=CompensationInfo(
                min_salary=45000,
                max_salary=60000,
                salary_currency="EUR",
                benefits=["Health insurance"],
            ),
            requirements=JobRequirements(
                required_skills=["Python", "Machine Learning"],
                experience_level="Mid-level",
                years_of_experience=3,
            ),
            responsibilities=["Build ML systems"],
            team_size="5-10 people",
            industry="Technology",
        )

    def analyze_job_for_candidate(self, *args, **kwargs):
        return FakeResult(
            {
                "fit_score": 0.8,
                "pros": ["Strong ML background"],
                "cons": ["Limited production experience"],
            }
        )

    def analyze_job_for_recruiter(self, *args, **kwargs):
        return FakeResult(
            {
                "market_competitiveness": "High",
                "candidate_pool_size": "Medium",
                "salary_appropriateness": "Fair",
            }
        )


class FakeMotivationLetterAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def generate_letter(self, request):
        metadata = MotivationLetterMetadata(
            generated_at=datetime(2026, 6, 30, 12, 0, 0),
            job_type=request.job_type,
            language=request.language,
            tone=request.tone,
            format=request.return_format,
            system_prompt_used=request.job_type,
            llm_model=self.config.model_name,
        )
        return MotivationLetter(
            content="Dear hiring team, this is a test motivation letter.",
            metadata=metadata,
        )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-credentials.json")
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    with patch("agents.base_agents.ChatGoogleGenerativeAI") as mock_llm, \
         patch("cv.agent.genai.Client") as mock_cv_client, \
         patch("jobs.agent.genai.Client") as mock_jobs_client:
        mock_llm.return_value = MagicMock()
        mock_cv_client.return_value = MagicMock()
        mock_jobs_client.return_value = MagicMock()

        from main import app
        import cv.route as cv_route
        import jobs.route as jobs_route
        import motivation_letter.route as ml_route

        config = AgentConfig(config_path=Path("config/agent_config.yaml"))

        cv_route.agent = FakeCVAgent(config)
        jobs_route.agent = FakeJobAgent(config)
        ml_route.agent = FakeMotivationLetterAgent(config)

        return TestClient(app)


def test_agent_config_loads_from_yaml(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-credentials.json")

    config = AgentConfig(config_path="config/agent_config.yaml")

    assert config.provider == "vertex"
    assert config.model_name == "gemini-2.5-flash"
    assert config.temperature == 0.7
    assert config.max_history == 50
    assert config.project_id == "test-project"
    assert config.location == "us-central1"


def test_cv_extract_uses_yaml_config(client):
    response = client.post(
        "/api/cv/extract",
        files={"file": ("cv.pdf", io.BytesIO(b"pdf content"), "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "CV extraction successful"
    assert data["data"]["personal_info"]["name"] == "Clement Suto"


def test_cv_analyze_uses_yaml_config(client):
    response = client.post(
        "/api/cv/analyze",
        files={"file": ("cv.pdf", io.BytesIO(b"pdf content"), "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "CV analysis successful"
    assert data["candidate"] == "Clement Suto"
    assert data["analysis"]["fit_score"] == 0.85


def test_job_extract_uses_yaml_config(client):
    response = client.post(
        "/api/jobs/extract",
        data={"job_text": "Ingénieur en IA, CDI, Paris, Python, ML"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job extraction successful"
    assert data["job_title"] == "Ingénieur en IA"
    assert data["company"] == "Tech Corp France"


def test_job_analyze_uses_yaml_config(client):
    job_data = JobPosition(
        job_title="Ingénieur en IA",
        company="Tech Corp France",
        location="Paris",
        contract_type="CDI",
        compensation=CompensationInfo(
            min_salary=45000,
            max_salary=60000,
            salary_currency="EUR",
            benefits=["Health insurance"],
        ),
        requirements=JobRequirements(
            required_skills=["Python", "Machine Learning"],
            experience_level="Mid-level",
            years_of_experience=3,
        ),
        responsibilities=["Build ML systems"],
        team_size="5-10 people",
        industry="Technology",
    ).model_dump_json()

    response = client.post("/api/jobs/analyze", data={"job_data": job_data})

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job analysis successful"
    assert data["candidate_analysis"]["fit_score"] == 0.8
    assert data["recruiter_analysis"]["market_competitiveness"] == "High"


def test_motivation_letter_generate_uses_yaml_config(client):
    cv = CVInformation(
        personal_info=PersonalInfo(
            name="John Doe",
            email="john@example.com",
            phone="+33612345678",
        ),
        experiences=[
            Experience(
                job_title="Senior AI Engineer",
                company="Tech Corp",
                start_date="2022",
                end_date="Present",
                description="Built ML systems",
            )
        ],
        skills=[RawSkill(name="Python"), RawSkill(name="ML")],
    )

    job = JobPosition(
        job_title="AI Engineer",
        company="Startup XYZ",
        location="Paris, France",
        description="Looking for AI expert",
        contract_type="CDI",
    )

    payload = {
        "cv_info": cv.model_dump(),
        "job_info": job.model_dump(),
        "job_type": "startup",
        "language": "fr",
        "tone": "professional",
        "return_format": "txt",
    }

    response = client.post("/api/motivation-letter/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["content"]
    assert data["metadata"]["job_type"] == "startup"
    assert data["metadata"]["llm_model"] == "gemini-2.5-flash"