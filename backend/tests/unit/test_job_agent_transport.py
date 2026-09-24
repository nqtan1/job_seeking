from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from infrastructure.agents.agent_config import AgentConfig
from infrastructure.jobs.analysis.agent import JobExtractionAgent
from domain.jobs.schema import JobPosition


def _build_model_mock():
    model = MagicMock()
    model.with_structured_output.return_value = model
    model.invoke.return_value = MagicMock(name="structured_response")
    return model


def test_extract_job_uses_gemini_file_upload(tmp_path):
    pdf_path = tmp_path / "job.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    mock_model = _build_model_mock()
    mock_file = SimpleNamespace(state=SimpleNamespace(name="READY"), uri="gemini-file-uri", name="job-file")
    mock_client = MagicMock()
    mock_client.files.upload.return_value = mock_file

    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model), patch(
        "infrastructure.jobs.analysis.agent.genai.Client", return_value=mock_client
    ):
        agent = JobExtractionAgent(
            config=AgentConfig(
                provider="api_key",
                api_key="test-api-key",
                model_name="gemini-2.5-flash",
            )
        )

        result = agent.extract_job(
            file_path=str(pdf_path),
            message="Extract job details",
            output_schema=JobPosition,
        )

    assert result is mock_model.invoke.return_value
    mock_client.files.upload.assert_called_once_with(file=str(pdf_path))

    human_message = mock_model.invoke.call_args.args[0][1]
    assert human_message.content[0]["text"] == "Extract job details"
    assert human_message.content[1]["type"] == "file"
    assert human_message.content[1]["file_id"] == "gemini-file-uri"
    assert human_message.content[1]["mime_type"] == "application/pdf"
    assert "data" not in human_message.content[1]


def test_extract_job_uses_vertex_base64_payload(tmp_path):
    pdf_path = tmp_path / "job.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    mock_model = _build_model_mock()

    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model), patch(
        "infrastructure.jobs.analysis.agent.genai.Client"
    ) as mock_client:
        agent = JobExtractionAgent(
            config=AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )

        result = agent.extract_job(
            file_path=Path(pdf_path),
            message="Extract job details",
            output_schema=JobPosition,
        )

    assert result is mock_model.invoke.return_value
    mock_client.assert_not_called()

    human_message = mock_model.invoke.call_args.args[0][1]
    assert human_message.content[0]["text"] == "Extract job details"
    assert human_message.content[1]["type"] == "file"
    assert human_message.content[1]["source_type"] == "base64"
    assert human_message.content[1]["mime_type"] == "application/pdf"
    assert human_message.content[1]["data"]


def test_extract_job_uses_raw_text_without_files():
    mock_model = _build_model_mock()

    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI", return_value=mock_model), patch(
        "infrastructure.jobs.analysis.agent.genai.Client"
    ) as mock_client:
        agent = JobExtractionAgent(
            config=AgentConfig(
                provider="vertex",
                project_id="test-project",
                location="us-central1",
                model_name="gemini-2.5-flash",
            )
        )

        result = agent.extract_job(
            job_text="Ingénieur IA, CDI, Paris",
            message="Extract job details",
            output_schema=JobPosition,
        )

    assert result is mock_model.invoke.return_value


@patch("pdfplumber.open")
def test_extract_job_with_qwen(mock_pdfplumber, tmp_path):
    pdf_path = tmp_path / "job.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    # Mock pdfplumber context manager and page extraction
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "This is my job text"
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.return_value.__enter__.return_value = mock_pdf

    mock_model = _build_model_mock()

    with patch("infrastructure.agents.base_agents.ChatOpenAI", return_value=mock_model):
        agent = JobExtractionAgent(
            config=AgentConfig(
                provider="qwen",
                qwen_base_url="http://vllm-endpoint/v1",
                qwen_api_key="test-key",
                model_name="Qwen/Qwen2.5-7B-Instruct",
            )
        )

        result = agent.extract_job(
            file_path=str(pdf_path),
            message="Extract job details",
            output_schema=JobPosition,
        )

    assert result is mock_model.invoke.return_value
    # Verify the model was invoked with the extracted text in the message
    human_message = mock_model.invoke.call_args.args[0][1]
    assert isinstance(human_message.content, str)
    assert "This is my job text" in human_message.content
    assert "Extract job details" in human_message.content


def test_extract_job_with_qwen_scanned_pdf(tmp_path):
    pdf_path = tmp_path / "scanned_job.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    # Mock pdfplumber context manager to return empty pages / empty text
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "  \n  " # Pure whitespace/scanned
    mock_pdf.pages = [mock_page]

    with patch("pdfplumber.open", return_value=MagicMock(__enter__=MagicMock(return_value=mock_pdf))):
        agent = JobExtractionAgent(
            config=AgentConfig(
                provider="qwen",
                qwen_base_url="http://vllm-endpoint/v1",
                qwen_api_key="test-key",
                model_name="Qwen/Qwen2.5-7B-Instruct",
            )
        )

        import pytest
        with pytest.raises(RuntimeError, match="empty or scanned"):
            agent.extract_job(
                file_path=str(pdf_path),
                message="Extract job details",
                output_schema=JobPosition,
            )


