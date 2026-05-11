import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

from cv.schema import CVInformation, PersonalInfo

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

@pytest.fixture
def mock_extracted_cv():
    """
    Pre-built mock extraction result
    """
    
    return CVInformation(
        personal_info=PersonalInfo(
            name="Clement Suto",
            email="clement_suto@example.com",
            phone="+33123456789", 
            address="Paris, France"
        ),
        formations=[],
        experiences=[],
        skills=[]
    )
    
def test_extract_cv_success(client, mock_extracted_cv):
    """
    Test successful CV extraction endpoint
    """
    with patch("cv.agent.CVAnalysisAgent.extract_cv") as mock_extract:
        mock_extract.return_value = mock_extracted_cv
        
        # Create mock file 
        response = client.post(
            "/api/cv/extract", 
            files={
                "file": ("test.pdf", io.BytesIO(b"pdf content to test"), "application/pdf")
            }
        )
        
        assert response.status_code == 200 
        data = response.json()
        assert data["message"] == "CV extraction successful"
        assert data["data"]["personal_info"]["name"] == "Clement Suto"
        assert "extract_path" in data
        assert "result_folder" in data
    
def test_extract_cv_invalid_file(client):
    """
    Test extraction with invalid file type
    """
    response = client.post(
        "/api/cv/extract", 
        files={
            "file": ("text_api.exe", io.BytesIO(b"malicious"), "application/x-msdownload")
        }
    )
    
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
    
def test_extract_cv_no_input(client):
    """
    Test extraction without file or file_path
    """
    response = client.post("/api/cv/extract")
    
    assert response.status_code == 400
    assert "Provide either" in response.json()["detail"]
    
def test_analyze_cv_from_file(client, mock_extracted_cv):
    """
    Test analysis from uploaded file
    """
    mock_analysis = Mock()
    mock_analysis.model_dump.return_value = {"fit_score": 0.85}
    mock_analysis.model_dump_json.return_value = '{"fit_score": 0.85}'
    
    with patch("cv.agent.CVAnalysisAgent.extract_cv") as mock_extract, patch("cv.agent.CVAnalysisAgent.analyze_cv") as mock_analyze:
        mock_extract.return_value = mock_extracted_cv
        mock_analyze.return_value = mock_analysis
            
        response = client.post(
            "/api/cv/analyze", 
            files={
                "file": ("test_analyze_cv.pdf",
                         io.BytesIO(b"pdf content"),
                         "application/pdf")
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["candidate"] == "Clement Suto"
        assert "analyze_path" in data
