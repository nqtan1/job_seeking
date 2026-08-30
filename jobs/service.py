from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from jobs.agent import JobExtractionAgent
from jobs.schema import CandidateAnalysis, JobPosition, RecruiterAnalysis
from utils.logger import get_logger


class JobService:
    def __init__(self, agent: JobExtractionAgent, logger_name: str = "jobs.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="jobs_api.log", level="INFO")
        self.allowed_extensions = {".pdf", ".txt", ".jpg", ".jpeg", ".png", ".img"}
        self.max_file_size = 10 * 1024 * 1024
        self.upload_base_dir = Path(__file__).resolve().parent.parent / "db/jobs/uploads"
        self.upload_base_dir.mkdir(parents=True, exist_ok=True)

    def _get_upload_folder(self) -> Path:
        date_folder = datetime.now().strftime("%Y-%m-%d")
        upload_dir = self.upload_base_dir / date_folder
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    def _get_result_folders(self, company: str, job_title: str) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder_name = f"{timestamp}_{company}_{job_title}".replace(" ", "_").replace("/", "_")

        extraction_dir = Path(__file__).resolve().parent.parent / "db/jobs/extract" / folder_name
        analysis_dir = Path(__file__).resolve().parent.parent / "db/jobs/analyze" / folder_name

        extraction_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Using job result folders: extraction=%s analysis=%s",
            extraction_dir,
            analysis_dir,
        )
        return extraction_dir, analysis_dir

    def _sanitize_filename(self, filename: str) -> str:
        filename = unicodedata.normalize("NFKD", filename)
        filename = filename.encode("ascii", "ignore").decode("ascii")
        filename = re.sub(r"[^\w\s.-]", "_", filename)
        filename = re.sub(r"[\s_]+", "_", filename)
        return filename.rstrip("_")

    async def _validate_and_get_file_path(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        operation: str,
    ) -> tuple[str, str]:
        self.logger.info(
            "%s validation started with file_present=%s file_path_present=%s",
            operation,
            bool(file),
            bool(file_path),
        )

        if file and file_path:
            self.logger.warning("%s: Both file and file_path provided, using file upload", operation)

        if file:
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in self.allowed_extensions:
                raise HTTPException(status_code=400, detail="File type not allowed (PDF, TXT, JPG, PNG, IMG)")

            file_content = await file.read()
            if len(file_content) > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File size exceeds {self.max_file_size // (1024 * 1024)} MB limit",
                )

            await file.seek(0)
            sanitized_filename = self._sanitize_filename(file.filename)
            upload_dir = self._get_upload_folder()
            saved_path = upload_dir / sanitized_filename
            with open(saved_path, "wb") as handle:
                handle.write(file_content)

            self.logger.info("File saved: %s (original: %s)", saved_path, file.filename)
            return str(saved_path), file.filename

        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            file_extension = path.suffix.lower()
            if file_extension not in self.allowed_extensions:
                raise HTTPException(status_code=400, detail="File type not allowed (PDF, TXT, JPG, PNG, IMG)")

            if path.stat().st_size > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File size exceeds {self.max_file_size // (1024 * 1024)} MB limit",
                )

            return file_path, path.name

        raise HTTPException(status_code=400, detail="Provide either 'file' (upload), 'file_path', or 'job_text' (raw text)")

    async def _get_job_information(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        job_data: Optional[str],
    ) -> JobPosition:
        if job_data and job_data.strip():
            try:
                if job_data.strip().startswith("{"):
                    return JobPosition(**json.loads(job_data))
                job_text = job_data
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(exc)}") from exc

        if job_text:
            return self.agent.extract_job(
                job_text=job_text,
                message="Extract all information from this job description",
                output_schema=JobPosition,
            )

        if file:
            processed_file_path, _ = await self._validate_and_get_file_path(file, None, "Analyze")
            return self.agent.extract_job(
                file_path=processed_file_path,
                message="Extract all information from this job description",
                output_schema=JobPosition,
            )

        if file_path:
            processed_file_path, _ = await self._validate_and_get_file_path(None, file_path, "Analyze")
            return self.agent.extract_job(
                file_path=processed_file_path,
                message="Extract all information from this job description",
                output_schema=JobPosition,
            )

        raise HTTPException(status_code=400, detail="Provide file, file_path, job_text, or job_data")

    def extract_job(
        self,
        file: Optional[UploadFile] = None,
        file_path: Optional[str] = None,
        job_text: Optional[str] = None,
    ) -> dict:
        if job_text:
            extracted_data = self.agent.extract_job(
                job_text=job_text,
                message="Extract all information from this job description",
                output_schema=JobPosition,
            )
        elif file:
            raise RuntimeError("Use extract_job_async for file uploads")
        elif file_path:
            extracted_data = self.agent.extract_job(
                file_path=file_path,
                message="Extract all information from this job description",
                output_schema=JobPosition,
            )
        else:
            raise HTTPException(status_code=400, detail="Provide either 'file', 'file_path', or 'job_text'")

        extraction_dir, _ = self._get_result_folders(extracted_data.company, extracted_data.job_title)
        extract_path = extraction_dir / "extraction.json"
        with open(extract_path, "w", encoding="utf-8") as handle:
            handle.write(extracted_data.model_dump_json(indent=2))

        return {
            "message": "Job extraction successful",
            "job_title": extracted_data.job_title,
            "company": extracted_data.company,
            "data": extracted_data.model_dump(),
            "extract_path": str(extract_path),
            "result_folder": str(extraction_dir),
        }

    async def extract_job_from_input(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
    ) -> dict:
        if job_text:
            return self.extract_job(job_text=job_text)

        if file:
            processed_file_path, _ = await self._validate_and_get_file_path(file, None, "Extract")
            return self.extract_job(file_path=processed_file_path)

        if file_path:
            processed_file_path, _ = await self._validate_and_get_file_path(None, file_path, "Extract")
            return self.extract_job(file_path=processed_file_path)

        raise HTTPException(status_code=400, detail="Provide either 'file', 'file_path', or 'job_text'")

    async def analyze_job_candidate(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        job_data: Optional[str],
    ) -> dict:
        job_information = await self._get_job_information(file, file_path, job_text, job_data)
        candidate_analysis = self.agent.analyze_job_for_candidate(
            job_information=job_information,
            output_schema=CandidateAnalysis,
            message="Analyze this job posting from a candidate's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company, job_information.job_title)
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        candidate_analysis_path = analysis_dir / "candidate_analysis.json"
        with open(candidate_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(candidate_analysis.model_dump_json(indent=2))

        return {
            "message": "Candidate analysis successful",
            "job_title": job_information.job_title,
            "company": job_information.company,
            "job_information": job_information.model_dump(),
            "candidate_analysis": candidate_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "candidate_analysis_path": str(candidate_analysis_path),
        }

    async def analyze_job_recruiter(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        job_data: Optional[str],
    ) -> dict:
        job_information = await self._get_job_information(file, file_path, job_text, job_data)
        recruiter_analysis = self.agent.analyze_job_for_recruiter(
            job_information=job_information,
            output_schema=RecruiterAnalysis,
            message="Analyze this job posting from a recruiter's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company, job_information.job_title)
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        recruiter_analysis_path = analysis_dir / "recruiter_analysis.json"
        with open(recruiter_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(recruiter_analysis.model_dump_json(indent=2))

        return {
            "message": "Recruiter analysis successful",
            "job_title": job_information.job_title,
            "company": job_information.company,
            "job_information": job_information.model_dump(),
            "recruiter_analysis": recruiter_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "recruiter_analysis_path": str(recruiter_analysis_path),
        }

    async def analyze_job(self, file: Optional[UploadFile], file_path: Optional[str], job_text: Optional[str], job_data: Optional[str]) -> dict:
        job_information = await self._get_job_information(file, file_path, job_text, job_data)
        candidate_analysis = self.agent.analyze_job_for_candidate(
            job_information=job_information,
            output_schema=CandidateAnalysis,
            message="Analyze this job posting from a candidate's perspective",
        )
        recruiter_analysis = self.agent.analyze_job_for_recruiter(
            job_information=job_information,
            output_schema=RecruiterAnalysis,
            message="Analyze this job posting from a recruiter's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company, job_information.job_title)
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        candidate_analysis_path = analysis_dir / "candidate_analysis.json"
        with open(candidate_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(candidate_analysis.model_dump_json(indent=2))

        recruiter_analysis_path = analysis_dir / "recruiter_analysis.json"
        with open(recruiter_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(recruiter_analysis.model_dump_json(indent=2))

        return {
            "message": "Job analysis successful",
            "job_title": job_information.job_title,
            "company": job_information.company,
            "job_information": job_information.model_dump(),
            "candidate_analysis": candidate_analysis.model_dump(),
            "recruiter_analysis": recruiter_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "candidate_analysis_path": str(candidate_analysis_path),
            "recruiter_analysis_path": str(recruiter_analysis_path),
        }