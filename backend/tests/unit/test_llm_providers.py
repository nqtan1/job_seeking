import os
from unittest.mock import patch, MagicMock
import pytest

from infrastructure.agents.agent_config import AgentConfig
from infrastructure.agents.base_agents import BaseAgent
from langchain_openai import ChatOpenAI


def test_agent_config_qwen_valid(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/v1")
    monkeypatch.setenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.setenv("QWEN_API_KEY", "secret-qwen-key")

    config = AgentConfig()

    assert config.provider == "qwen"
    assert config.model_name == "Qwen/Qwen2.5-7B-Instruct"
    assert config.qwen_base_url == "http://vllm-endpoint/v1"
    assert config.qwen_api_key == "secret-qwen-key"


def test_agent_config_qwen_url_sanitization(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

    # URL missing /v1 suffix
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint")
    config = AgentConfig()
    assert config.qwen_base_url == "http://vllm-endpoint/v1"

    # URL with trailing slashes and /chat/completions suffix
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/v1/chat/completions/")
    config2 = AgentConfig()
    assert config2.qwen_base_url == "http://vllm-endpoint/v1"

    # URL with /chat suffix
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/chat")
    config3 = AgentConfig()
    assert config3.qwen_base_url == "http://vllm-endpoint/v1"


def test_agent_config_qwen_missing_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)
    monkeypatch.setenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

    with pytest.raises(ValueError, match="Qwen mode requires QWEN_BASE_URL env var"):
        AgentConfig()


def test_agent_config_qwen_missing_model_name(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/v1")
    monkeypatch.delenv("QWEN_MODEL_NAME", raising=False)

    with pytest.raises(ValueError, match="Qwen mode requires QWEN_MODEL_NAME env var"):
        AgentConfig()


def test_agent_config_llm_provider_switching(monkeypatch):
    # Test fallback to gemini (vertex) when LLM_PROVIDER is not set
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    config = AgentConfig()
    assert config.provider == "vertex"

    # Test switching specifically to gemini
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    config2 = AgentConfig()
    assert config2.provider == "vertex"


@patch("infrastructure.agents.base_agents.ChatOpenAI")
def test_base_agent_initialization_with_qwen(mock_chat_openai, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/v1")
    monkeypatch.setenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.setenv("QWEN_API_KEY", "secret-qwen-key")

    mock_model_instance = MagicMock()
    mock_chat_openai.return_value = mock_model_instance

    class DummyAgent(BaseAgent):
        pass

    agent = DummyAgent()

    # Verify that ChatOpenAI was instantiated with the correct parameters
    mock_chat_openai.assert_called_once_with(
        base_url="http://vllm-endpoint/v1",
        api_key="secret-qwen-key",
        model="Qwen/Qwen2.5-7B-Instruct",
        temperature=0.7,
    )
    assert agent.model == mock_model_instance


@patch("infrastructure.agents.base_agents.ChatOpenAI")
def test_base_agent_initialization_with_qwen_missing_api_key(mock_chat_openai, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm-endpoint/v1")
    monkeypatch.setenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    mock_model_instance = MagicMock()
    mock_chat_openai.return_value = mock_model_instance

    class DummyAgent(BaseAgent):
        pass

    agent = DummyAgent()

    # Verify that ChatOpenAI was instantiated with "placeholder" key
    mock_chat_openai.assert_called_once_with(
        base_url="http://vllm-endpoint/v1",
        api_key="placeholder",
        model="Qwen/Qwen2.5-7B-Instruct",
        temperature=0.7,
    )
    assert agent.model == mock_model_instance


def test_agent_config_section_loading(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    
    mock_data = {
        "cv": {
            "provider": "qwen",
            "model_name": "qwen2.5-coder-14b",
            "temperature": 0.2,
        },
        "fit": {
            "provider": "vertex",
            "model_name": "gemini-2.5-flash",
            "temperature": 0.5,
        }
    }
    
    with patch.object(AgentConfig, "_load_config_file", return_value=mock_data):
        # Load fit section
        config_fit = AgentConfig(config_path="dummy.yaml", section="fit")
        assert config_fit.provider == "vertex"
        assert config_fit.model_name == "gemini-2.5-flash"
        assert config_fit.temperature == 0.5

        # Load cv section
        config_cv = AgentConfig(config_path="dummy.yaml", section="cv")
        assert config_cv.provider == "qwen"
        assert config_cv.model_name == "qwen2.5-coder-14b"
        assert config_cv.temperature == 0.2
