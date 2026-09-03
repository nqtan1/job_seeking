import io
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from jobs.schema import JobPosition, CompensationInfo, JobRequirements, CandidateAnalysis, RecruiterAnalysis

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
        job_title="Ingénieur en IA",
        company="Tech Corp France",
        location="Paris 75008",
        contract_type="CDI",
        compensation=CompensationInfo(
            min_salary=45000,
            max_salary=60000,
            salary_currency="EUR",
            benefits=["Health insurance", "RTT"]
        ),
        requirements=JobRequirements(
            required_skills=["Python", "Machine Learning", "TensorFlow"],
            experience_level="Mid-level",
            years_of_experience=3
        ),
        responsibilities=["Develop ML models", "Optimize algorithms"],
        team_size="5-10 people",
        industry="Technology"
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
    with patch("jobs.agent.JobExtractionAgent.extract_job") as mock_extract:
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
    
    with patch("jobs.agent.JobExtractionAgent.extract_job") as mock_extract:
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
    with patch("jobs.agent.JobExtractionAgent.extract_job") as mock_extract, \
         patch("jobs.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("jobs.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
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
    
    with patch("jobs.agent.JobExtractionAgent.extract_job") as mock_extract, \
         patch("jobs.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("jobs.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
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
        job_title="Data Scientist",
        company="AI Startup",
        location="Lyon",
        contract_type="CDI",
        requirements=JobRequirements(
            required_skills=["Python", "SQL"],
            experience_level="Mid-level"
        )
    )
    job_data_json = job_position.model_dump_json()
    
    with patch("jobs.agent.JobExtractionAgent.analyze_job_for_candidate") as mock_candidate, \
         patch("jobs.agent.JobExtractionAgent.analyze_job_for_recruiter") as mock_recruiter:
        
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
