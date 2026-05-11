import pytest
from pathlib import Path
import tempfile

from cv.route import _sanitize_filename, _validate_and_get_file_path

class TestSanitizeFileName: 
    def test_removes_accents(self):
        assert _sanitize_filename("Quoc_Tân_NGUYỄN.pdf") == "Quoc_Tan_NGUYEN.pdf"
        
    def test_replace_special_chars(self):
        assert _sanitize_filename("CV@2025#Final.pdf") == "CV_2025_Final.pdf"
        
    def test_handle_spaces(self):
        assert _sanitize_filename("My CV File.pdf") == "My_CV_File.pdf"
    
    def test_no_trailing_underscore(self):
        assert _sanitize_filename("test___").endswith("_") == False

    def test_preserves_valid_chars(self):
        assert _sanitize_filename("cv-2025.v1.0.pdf") == "cv-2025.v1.0.pdf"
    
class TestValidateAndGetFilePath: 
    @pytest.mark.asyncio
    async def test_valid_upload(self):
        """
        Test file upload with valid PDF
        """
        from fastapi import UploadFile
        import io
        
        file = UploadFile(
            filename="test_function.pdf",
            file=io.BytesIO(b"mock pdf content")
        )
        
        file_path, filename = await _validate_and_get_file_path(file, None)
        assert filename == "test_function.pdf"
        assert Path(file_path).exists()
        
    @pytest.mark.asyncio
    async def test_invalid_extension(self):
        """
        Test rejection of unsupported file types
        """
        from fastapi import UploadFile, HTTPException
        import io
        
        file = UploadFile(
            filename="test_function.exe", 
            file=io.BytesIO(b"malicious")
        )
        
        with pytest.raises(HTTPException) as exc: 
            await _validate_and_get_file_path(file, None)
        assert exc.value.status_code == 400
        
    @pytest.mark.asyncio
    async def test_file_size_limit(self):
        """
        Test rejection of oversize files
        """
        from fastapi import UploadFile, HTTPException
        import io
        
        file = UploadFile(
            filename="test_huge_file.pdf",
            file=io.BytesIO(b"x" * (11 * 1024 * 1024))
        )
        
        with pytest.raises(HTTPException) as exc: 
            await _validate_and_get_file_path(file, None)
        assert exc.value.status_code == 413