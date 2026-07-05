from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agents.agent_config import AgentConfig
from cv.agent import CVAnalysisAgent
from cv.schema import CVInformation


def _build_model_mock():
    model = MagicMock()
    model.with_structured_output.return_value = model
    model.invoke.return_value = MagicMock(name="structured_response")
    return model


def test_extract_cv_uses_gemini_file_upload(tmp_path):
    pdf_path = tmp_path / "cv.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    mock_model = _build_model_mock()
    mock_file = SimpleNamespace(state=SimpleNamespace(name="READY"), uri="gemini-file-uri", name="cv-file")
    mock_client = MagicMock()
    mock_client.files.upload.return_value = mock_file

    with patch("agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model), patch(
        "cv.agent.genai.Client", return_value=mock_client
    ):
        agent = CVAnalysisAgent(
            config=AgentConfig(
                provider="api_key",
                api_key="test-api-key",
                model_name="gemini-2.5-flash",
            )
        )

        result = agent.extract_cv(
            file_path=str(pdf_path),
            message="Extract CV details",
            output_schema=CVInformation,
        )

    assert result is mock_model.invoke.return_value
    mock_client.files.upload.assert_called_once_with(file=str(pdf_path))

    human_message = mock_model.invoke.call_args.args[0][1]
    assert human_message.content[0]["text"] == "Extract CV details"
    assert human_message.content[1]["type"] == "file"
    assert human_message.content[1]["file_id"] == "gemini-file-uri"
    assert human_message.content[1]["mime_type"] == "application/pdf"
    assert "data" not in human_message.content[1]


def test_extract_cv_uses_vertex_base64_payload(tmp_path):
    pdf_path = tmp_path / "cv.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    mock_model = _build_model_mock()

    with patch("agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model), patch(
        "cv.agent.genai.Client"
    ) as mock_client:
        agent = CVAnalysisAgent(
            config=AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )

        result = agent.extract_cv(
            file_path=Path(pdf_path),
            message="Extract CV details",
            output_schema=CVInformation,
        )

    assert result is mock_model.invoke.return_value
    mock_client.assert_not_called()

    human_message = mock_model.invoke.call_args.args[0][1]
    assert human_message.content[0]["text"] == "Extract CV details"
    assert human_message.content[1]["type"] == "file"
    assert human_message.content[1]["source_type"] == "base64"
    assert human_message.content[1]["mime_type"] == "application/pdf"
    assert human_message.content[1]["data"]