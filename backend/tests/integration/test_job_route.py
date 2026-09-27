import io
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from domain.jobs.schema import JobPosition, CompensationInfo, CandidateAnalysis, RecruiterAnalysis, CompanyInfo, Badges, Profile, AboutCompany, Modalities, SourceMeta

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

@pytest.fixture
def mock_job_position():
    """
    Pre-built mock job position extraction result
    """
    return JobPosition(
        title="Ingénieur en IA",
        company=CompanyInfo(name="Tech Corp France", type="employer"),
        badges=Badges(
            contract_type="CDI",
            location="Paris 75008",
            experience_level="Mid-level",
        ),
        about_company=AboutCompany(summary=""),
        missions=["Develop ML models", "Optimize algorithms"],
        tech_stack=[],
        working_methods=[],
        profile=Profile(
            technical_skills=["Python", "Machine Learning", "TensorFlow"],
        ),
        modalities=Modalities(),
        compensation=CompensationInfo(
            min_salary=45000,
            max_salary=60000,
            salary_currency="EUR",
            benefits=["Health insurance", "RTT"]
        ),
        source_meta=SourceMeta(industry="Technology"),
    )

@pytest.fixture
def mock_candidate_analysis():
    """
    Pre-built mock candidate analysis result
    """
    mock_analysis = Mock()
    mock_analysis.model_dump.return_value = {
        "fit_score": 0.8,
        "pros": ["Strong ML background"],
        "cons": ["Limited production experience"]
    }
    mock_analysis.model_dump_json.return_value = json.dumps({
        "fit_score": 0.8,
        "pros": ["Strong ML background"],
        "cons": ["Limited production experience"]
    })
    return mock_analysis

@pytest.fixture
def mock_recruiter_analysis():
    """
    Pre-built mock recruiter analysis result
    """
    mock_analysis = Mock()
    mock_analysis.model_dump.return_value = {
        "market_competitiveness": "High",
        "candidate_pool_size": "Medium",
        "salary_appropriateness": "Fair"
    }
    mock_analysis.model_dump_json.return_value = json.dumps({
        "market_competitiveness": "High",
        "candidate_pool_size": "Medium",
        "salary_appropriateness": "Fair"
    })
    return mock_analysis

def test_extract_job_success(client, mock_job_position):
    """
    Test successful job extraction endpoint
    """
    with patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.extract_job") as mock_extract:
        mock_extract.return_value = mock_job_position
        
        response = client.post(
            "/api/jobs/extract",
            files={
                "file": ("job_posting.pdf", io.BytesIO(b"pdf content"), "application/pdf")
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Job extraction successful"
        assert data["job_title"] == "Ingénieur en IA"
        assert data["company"] == "Tech Corp France"
        assert "extract_path" in data
        assert "result_folder" in data

def test_extract_job_invalid_file(client):
    """
    Test extraction with invalid file type
    """
    response = client.post(
        "/api/jobs/extract",
        files={
            "file": ("malware.exe", io.BytesIO(b"malicious"), "application/x-msdownload")
        }
    )
    
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]

def test_extract_job_no_input(client):
    """
    Test extraction without file or file_path or job_text
    """
    response = client.post("/api/jobs/extract")
    
    assert response.status_code == 400
    assert "Provide either" in response.json()["detail"]

def test_extract_job_from_text(client, mock_job_position):
    """
    Test extraction from raw job text
    """
    job_text = "Ingénieur en IA, CDI, Paris, Salaire 45k-60k"
    
    with patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.extract_job") as mock_extract:
        mock_extract.return_value = mock_job_position
        
        response = client.post(
            "/api/jobs/extract",
            data={"job_text": job_text}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Job extraction successful"
        assert data["job_title"] == "Ingénieur en IA"

def test_analyze_job_from_file(client, mock_job_position, mock_candidate_analysis, mock_recruiter_analysis):
    """
    Test analysis from uploaded file
    """
    with patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.extract_job") as mock_extract, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
        mock_extract.return_value = mock_job_position
        mock_candidate.return_value = mock_candidate_analysis
        mock_recruiter.return_value = mock_recruiter_analysis
        
        response = client.post(
            "/api/jobs/analyze",
            files={
                "file": ("job_description.pdf", io.BytesIO(b"pdf content"), "application/pdf")
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Job analysis successful"
        assert data["job_title"] == "Ingénieur en IA"
        assert data["company"] == "Tech Corp France"
        assert "candidate_analysis" in data
        assert "recruiter_analysis" in data

def test_analyze_job_from_text(client, mock_job_position, mock_candidate_analysis, mock_recruiter_analysis):
    """
    Test analysis from raw job text
    """
    job_text = "Ingénieur en IA, CDI, Paris, Salaire 45k-60k, Python required"
    
    with patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.extract_job") as mock_extract, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
        mock_extract.return_value = mock_job_position
        mock_candidate.return_value = mock_candidate_analysis
        mock_recruiter.return_value = mock_recruiter_analysis
        
        response = client.post(
            "/api/jobs/analyze",
            data={"job_text": job_text}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Job analysis successful"
        assert data["candidate_analysis"]["fit_score"] == 0.8

def test_analyze_job_from_job_data(client, mock_candidate_analysis, mock_recruiter_analysis):
    """
    Test analysis from pre-extracted job data JSON
    """
    job_position = JobPosition(
        title="Data Scientist",
        company=CompanyInfo(name="AI Startup", type="employer"),
        badges=Badges(
            contract_type="CDI",
            location="Lyon",
            experience_level="Mid-level",
        ),
        about_company=AboutCompany(summary=""),
        missions=[],
        tech_stack=[],
        working_methods=[],
        profile=Profile(
            technical_skills=["Python", "SQL"],
        ),
        modalities=Modalities(),
        source_meta=SourceMeta(),
    )
    job_data_json = job_position.model_dump_json()
    
    with patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
        mock_candidate.return_value = mock_candidate_analysis
        mock_recruiter.return_value = mock_recruiter_analysis
        
        response = client.post(
            "/api/jobs/analyze",
            data={"job_data": job_data_json}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_title"] == "Data Scientist"
        assert data["company"] == "AI Startup"

def test_analyze_job_no_input(client):
    """
    Test analysis without any input
    """
    response = client.post("/api/jobs/analyze")
    
    assert response.status_code == 400
    assert "Provide" in response.json()["detail"]

def test_extract_job_file_size_limit(client):
    """
    Test rejection of oversized files
    """
    response = client.post(
        "/api/jobs/extract",
        files={
            "file": ("huge_job.pdf", io.BytesIO(b"x" * (11 * 1024 * 1024)), "application/pdf")
        }
    )
    
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]

def test_extract_job_from_url(client, mock_job_position):
    """
    Test extraction from a URL.
    """
    mock_url = "https://example.com/job/123"
    mock_url_content = "<h1>Ingénieur en IA</h1><p>Company: Tech Corp France</p><p>Location: Paris</p>"
    
    with patch("application.jobs.analysis.service.JobService._is_url") as mock_is_url, \
         patch("application.jobs.analysis.service.JobService._fetch_url_content") as mock_fetch_url_content, \
         patch("infrastructure.jobs.analysis.agent.JobExtractionAgent.extract_job") as mock_extract:
        
        mock_is_url.return_value = True
        mock_fetch_url_content.return_value = mock_url_content
        mock_extract.return_value = mock_job_position

        response = client.post(
            "/api/jobs/extract",
            data={"job_text": mock_url}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Job extraction successful"
        assert data["job_title"] == "Ingénieur en IA"
        assert data["company"] == "Tech Corp France"
        mock_is_url.assert_called_once_with(mock_url)
        mock_fetch_url_content.assert_called_once_with(mock_url)
        mock_extract.assert_called_once()
