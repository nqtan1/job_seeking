import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

from domain.cv.schema import CVInformation, PersonalInfo

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
    with patch("infrastructure.cv.agent.CVAnalysisAgent.extract_cv") as mock_extract:
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
    
    with patch("infrastructure.cv.agent.CVAnalysisAgent.extract_cv") as mock_extract, patch("infrastructure.cv.agent.CVAnalysisAgent.analyze_cv") as mock_analyze:
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


def test_analyze_cv_prefers_file_when_cv_data_is_also_sent(client, mock_extracted_cv):
    mock_analysis = Mock()
    mock_analysis.model_dump.return_value = {"fit_score": 0.85}
    mock_analysis.model_dump_json.return_value = '{"fit_score": 0.85}'

    with patch("api.cv.agent.extract_cv") as mock_extract, patch("api.cv.agent.analyze_cv") as mock_analyze:
        mock_extract.return_value = mock_extracted_cv
        mock_analyze.return_value = mock_analysis

        response = client.post(
            "/api/cv/analyze",
            files={
                "file": ("test_analyze_cv.pdf", io.BytesIO(b"pdf content"), "application/pdf")
            },
            data={"cv_data": "not-a-valid-json-payload"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["candidate"] == "Clement Suto"
        mock_extract.assert_called_once()
        mock_analyze.assert_called_once()


def test_list_candidates_and_get_file(client, tmp_path):
    import workers.background as bg
    # Isolate DB
    temp_db = tmp_path / "test_cv_candidates.db"
    old_manager = bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = bg.BackgroundJobManager(db_path=str(temp_db))

    try:
        # Create a mock file on disk
        mock_cv_file = tmp_path / "john_doe_resume.pdf"
        mock_cv_file.write_bytes(b"John Doe CV file contents")

        # Save mock candidate with file_path in DB
        candidate_id = bg._BACKGROUND_JOB_MANAGER.save_candidate(
            tenant_id="test-tenant-cv",
            name="John Doe",
            email="john.doe@example.com",
            phone="12345",
            extracted_data_json='{}',
            file_path=str(mock_cv_file)
        )

        # 1. Test listing candidates
        response = client.get(
            "/api/cv/candidates",
            headers={"X-Tenant-ID": "test-tenant-cv"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "candidates" in data
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["name"] == "John Doe"
        assert data["candidates"][0]["candidate_id"] == candidate_id

        # 2. Test fetching candidate CV file
        response = client.get(
            f"/api/cv/candidates/{candidate_id}/file",
            headers={"X-Tenant-ID": "test-tenant-cv"}
        )
        assert response.status_code == 200
        assert response.content == b"John Doe CV file contents"

        # 3. Test multi-tenant isolation
        response = client.get(
            f"/api/cv/candidates/{candidate_id}/file",
            headers={"X-Tenant-ID": "different-tenant"}
        )
        assert response.status_code == 404

    finally:
        bg._BACKGROUND_JOB_MANAGER = old_manager


def test_candidate_file_strict_no_scanning(client, tmp_path):
    import workers.background as bg
    from api.cv import UPLOAD_BASE_DIR
    
    # Isolate DB
    temp_db = tmp_path / "test_cv_candidates_scanning.db"
    old_manager = bg._BACKGROUND_JOB_MANAGER
    bg._BACKGROUND_JOB_MANAGER = bg.BackgroundJobManager(db_path=str(temp_db))

    try:
        # Create a file in the uploads directory with candidate's name
        # but NOT registered as file_path in the DB candidate record.
        candidate_name = "Jane_Doe_Scam_Scan"
        unregistered_file = UPLOAD_BASE_DIR / f"{candidate_name}_resume.pdf"
        unregistered_file.write_bytes(b"Secret unregistered file content")

        # Save mock candidate with NO file_path (None) in DB
        candidate_id = bg._BACKGROUND_JOB_MANAGER.save_candidate(
            tenant_id="test-tenant-cv",
            name="Jane Doe Scam Scan",
            email="jane.doe@example.com",
            phone="98765",
            extracted_data_json='{}',
            file_path=None
        )

        # Fetch the candidate CV file. It should NOT find the unregistered file via scanning
        # and instead serve the dynamically generated compiler text fallback.
        response = client.get(
            f"/api/cv/candidates/{candidate_id}/file",
            headers={"X-Tenant-ID": "test-tenant-cv"}
        )
        assert response.status_code == 200
        assert b"CANDIDATE RESUME PROFILE" in response.content
        assert b"Secret unregistered file content" not in response.content

        # Clean up mock file
        if unregistered_file.exists():
            unregistered_file.unlink()

    finally:
        bg._BACKGROUND_JOB_MANAGER = old_manager
