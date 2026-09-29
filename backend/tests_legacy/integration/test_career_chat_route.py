from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from domain.cv.schema import CVInformation, PersonalInfo
from domain.jobs.schema import (
    AboutCompany,
    Badges,
    CompanyInfo,
    JobPosition,
    Modalities,
    Profile,
    SourceMeta,
)


class FakeCareerChatAgent:
    def __init__(self):
        self.conversation_history = []
        self.seeded_with = None
        self.last_message = None

    def seed_context(
        self, candidate_cv, job_information=None, fit_check=None, interview_kit=None
    ):
        self.seeded_with = {
            "candidate_cv": candidate_cv,
            "job_information": job_information,
            "fit_check": fit_check,
            "interview_kit": interview_kit,
        }
        self.conversation_history = ["<system context>"]

    def reply(self, message: str) -> str:
        self.last_message = message
        return (
            f"Coach reply to: {message} (history_len={len(self.conversation_history)})"
        )


def _build_client():
    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value = MagicMock()

        import api.career_chat as career_chat_route
        from main import app

        fake_agent = FakeCareerChatAgent()
        career_chat_route.agent = fake_agent
        return TestClient(app), fake_agent


def _cv():
    return CVInformation(
        personal_info=PersonalInfo(name="Jane Doe", phone="0600000000")
    ).model_dump()


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


def test_career_chat_message_without_job_or_history():
    client, fake_agent = _build_client()

    response = client.post(
        "/api/career-chat/message",
        json={"candidate_cv": _cv(), "message": "What should I improve on my CV?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "Coach reply to: What should I improve on my CV?" in data["reply"]
    assert fake_agent.seeded_with["job_information"] is None
    assert fake_agent.conversation_history == ["<system context>"]


def test_career_chat_message_replays_history_before_replying():
    client, fake_agent = _build_client()

    response = client.post(
        "/api/career-chat/message",
        json={
            "candidate_cv": _cv(),
            "job_information": _job(),
            "message": "And what about the tech stack?",
            "history": [
                {"role": "user", "content": "Am I a good fit for this job?"},
                {
                    "role": "assistant",
                    "content": "You have strong Python skills but lack Docker experience.",
                },
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "history_len=3" in data["reply"]  # seeded context + 2 replayed turns
    assert fake_agent.seeded_with["job_information"].company.name == "Acme"


def test_career_chat_message_requires_cv():
    client, _ = _build_client()

    response = client.post("/api/career-chat/message", json={"message": "Hello"})

    assert response.status_code == 422
