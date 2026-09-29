from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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
from infrastructure.agents.agent_config import AgentConfig
from infrastructure.career_chat.agent import RECENT_TURNS_KEPT, CareerChatAgent


def _build_agent(mock_model, max_history=10):
    with patch(
        "infrastructure.agents.base_agents.ChatGoogleGenerativeAI",
        return_value=mock_model,
    ):
        return CareerChatAgent(
            config=AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
                max_history=max_history,
            )
        )


def _cv():
    return CVInformation(
        personal_info=PersonalInfo(name="Jane Doe", phone="0600000000")
    )


def _job():
    return JobPosition(
        title="Backend Engineer",
        company=CompanyInfo(name="Acme"),
        badges=Badges(),
        about_company=AboutCompany(summary=""),
        profile=Profile(),
        modalities=Modalities(),
        source_meta=SourceMeta(),
    )


def test_seed_context_includes_cv_and_optional_sections():
    agent = _build_agent(MagicMock())

    agent.seed_context(candidate_cv=_cv())
    assert len(agent.conversation_history) == 1
    system_content = agent.conversation_history[0].content
    assert "Jane Doe" in system_content
    assert "JOB UNDER DISCUSSION" not in system_content

    agent.seed_context(candidate_cv=_cv(), job_information=_job())
    system_content = agent.conversation_history[0].content
    assert "JOB UNDER DISCUSSION" in system_content
    assert "Acme" in system_content


def test_truncate_history_smart_condenses_older_turns_via_summary():
    mock_model = MagicMock()
    mock_model.invoke.return_value = MagicMock(
        content="Candidate discussed backend role, gaps in Docker."
    )
    agent = _build_agent(mock_model, max_history=5)

    agent.seed_context(candidate_cv=_cv())
    for i in range(10):
        agent.conversation_history.append(HumanMessage(content=f"question {i}"))
        agent.conversation_history.append(AIMessage(content=f"answer {i}"))

    agent._truncate_history_smart()

    assert isinstance(agent.conversation_history[0], SystemMessage)  # seeded context
    assert isinstance(agent.conversation_history[1], SystemMessage)  # summary
    assert "Docker" in agent.conversation_history[1].content
    assert len(agent.conversation_history) == 2 + RECENT_TURNS_KEPT
    # The most recent turns must be preserved verbatim
    assert agent.conversation_history[-1].content == "answer 9"


def test_truncate_history_smart_falls_back_to_plain_truncation_on_summary_failure():
    mock_model = MagicMock()
    mock_model.invoke.side_effect = RuntimeError("local model unreachable")
    agent = _build_agent(mock_model, max_history=5)

    agent.seed_context(candidate_cv=_cv())
    for i in range(10):
        agent.conversation_history.append(HumanMessage(content=f"question {i}"))
        agent.conversation_history.append(AIMessage(content=f"answer {i}"))

    # Must not raise even though the summarization call fails
    agent._truncate_history_smart()

    assert isinstance(agent.conversation_history[0], SystemMessage)
    assert len(agent.conversation_history) == agent.config.max_history
    assert agent.conversation_history[-1].content == "answer 9"


def test_truncate_history_smart_noop_when_within_limit():
    agent = _build_agent(MagicMock(), max_history=50)
    agent.seed_context(candidate_cv=_cv())
    agent.conversation_history.append(HumanMessage(content="hi"))

    agent._truncate_history_smart()

    assert len(agent.conversation_history) == 2
