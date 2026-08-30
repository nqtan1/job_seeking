from unittest.mock import MagicMock, patch

from agents.agent_config import AgentConfig
from cv.schema import CVInformation, PersonalInfo, Experience, RawSkill
from fit.agent import FitAgent
from fit.schema import FitCheck
from jobs.schema import JobPosition


def _build_model_mock():
    model = MagicMock()
    model.with_structured_output.return_value = model
    model.invoke.return_value = MagicMock(name="structured_response")
    return model


def test_analyze_fit_uses_structured_prompt_and_payload():
    mock_model = _build_model_mock()

    with patch("agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model):
        agent = FitAgent(
            config=AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )

        candidate_cv = CVInformation(
            personal_info=PersonalInfo(name="John Doe", email="john@example.com", phone="+33612345678"),
            experiences=[Experience(job_title="ML Engineer", company="Example Corp", description="Built ML systems")],
            skills=[RawSkill(name="Python")],
        )
        job_information = JobPosition(
            job_title="AI Engineer",
            company="Startup XYZ",
            location="Paris",
            contract_type="CDI",
        )

        result = agent.analyze_fit(
            candidate_cv=candidate_cv,
            job_information=job_information,
            company_type="startup",
            output_schema=FitCheck,
            recruiter_attend={"must_have": ["Python"]},
        )

    assert result is mock_model.invoke.return_value
    human_message = mock_model.invoke.call_args.args[0][1]
    assert "Candidate CV" not in human_message.content
    assert "JOB INFORMATION:" in human_message.content
    assert "Startup XYZ" in human_message.content
    assert "RECRUITER CONDITIONS" in human_message.content
    system_message = mock_model.invoke.call_args.args[0][0]
    assert "startup" in system_message.content.lower()