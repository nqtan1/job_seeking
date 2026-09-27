import pytest
from unittest.mock import Mock

from fastapi import HTTPException

from application.jobs.analysis.service import JobService


@pytest.fixture
def job_service():
    return JobService(agent=Mock())


class TestValidateAndGetFilePath:
    @pytest.mark.asyncio
    async def test_file_path_outside_db_base_dir_is_rejected(self, job_service, tmp_path):
        """
        A client-supplied file_path pointing outside db_base_dir (e.g. arbitrary
        filesystem paths, or another tenant's upload directory reached via
        traversal) must be rejected rather than read.
        """
        outside_file = tmp_path / "not_in_db_dir.pdf"
        outside_file.write_bytes(b"mock pdf content")

        with pytest.raises(HTTPException) as exc:
            await job_service._validate_and_get_file_path(None, str(outside_file), "Test")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_file_path_traversal_is_rejected(self, job_service):
        """
        A file_path containing '..' segments that resolve outside db_base_dir
        must be rejected.
        """
        traversal_path = str(
            job_service.db_base_dir / "jobs" / "uploads" / ".." / ".." / ".." / "etc" / "passwd"
        )

        with pytest.raises(HTTPException) as exc:
            await job_service._validate_and_get_file_path(None, traversal_path, "Test")
        assert exc.value.status_code == 403
