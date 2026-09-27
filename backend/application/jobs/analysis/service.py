from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from infrastructure.jobs.analysis.agent import JobExtractionAgent
from domain.jobs.analysis.schema import CandidateAnalysis, JobPosition, RecruiterAnalysis
from application.jobs.analysis.parser import post_process_job_position
from utils.logger import get_logger
from workers.background import get_background_job_manager


class JobService:
    def __init__(self, agent: JobExtractionAgent, logger_name: str = "jobs.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="jobs_api.log", level="INFO")
        self.allowed_extensions = {".pdf", ".txt", ".jpg", ".jpeg", ".png", ".img"}
        self.max_file_size = 10 * 1024 * 1024
        
        # Set up clean data directory path supporting GCS FUSE
        data_dir_env = os.getenv("DATA_DIR")
        if data_dir_env:
            self.db_base_dir = Path(data_dir_env)
        else:
            self.db_base_dir = Path(__file__).resolve().parent.parent.parent.parent / "db"
            
        self.upload_base_dir = self.db_base_dir / "jobs" / "uploads"
        self.upload_base_dir.mkdir(parents=True, exist_ok=True)

    def _get_upload_folder(self) -> Path:
        date_folder = datetime.now().strftime("%Y-%m-%d")
        upload_dir = self.upload_base_dir / date_folder
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    def _get_result_folders(self, company: str, job_title: str) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder_name = f"{timestamp}_{company}_{job_title}".replace(" ", "_").replace("/", "_")

        extraction_dir = self.db_base_dir / "jobs" / "extract" / folder_name
        analysis_dir = self.db_base_dir / "jobs" / "analyze" / folder_name

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

    def _is_url(self, text: str) -> bool:
        """Checks if the given text is a valid URL."""
        return re.match(r'^https?://', text) is not None

    async def _fetch_url_content(self, url: str) -> str:
        """Fetches content from a URL and extracts text."""
        self.logger.info("Fetching content from URL: %s", url)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()  # Raise an exception for HTTP errors
                soup = BeautifulSoup(response.text, 'html.parser')
                # Attempt to find the main content area, common selectors for job descriptions
                for selector in ['div.job-description', 'div#jobDescriptionText', 'div.description', 'main', 'body']:
                    content_div = soup.select_one(selector)
                    if content_div:
                        return content_div.get_text(separator='\n', strip=True)
                return soup.get_text(separator='\n', strip=True) # Fallback to all text
        except httpx.HTTPStatusError as e:
            self.logger.error("HTTP error fetching URL %s: %s", url, e)
            raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch URL content: {e.response.status_code} - {e.response.text[:100]}")
        except httpx.RequestError as e:
            self.logger.error("Request error fetching URL %s: %s", url, e)
            raise HTTPException(status_code=500, detail=f"Failed to connect to URL: {e}")
        except Exception as e:
            self.logger.error("Error fetching or parsing URL %s: %s", url, e)
            raise HTTPException(status_code=500, detail=f"Error processing URL content: {e}")

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
            # Resolve and contain the path under db_base_dir so a client-supplied
            # file_path cannot read arbitrary files on disk (path traversal /
            # cross-tenant file access).
            resolved_path = Path(file_path).resolve()
            try:
                resolved_path.relative_to(self.db_base_dir.resolve())
            except ValueError:
                self.logger.warning("Rejected file_path outside of db_base_dir: %s", file_path)
                raise HTTPException(status_code=403, detail="File path is not allowed")

            if not resolved_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            file_extension = resolved_path.suffix.lower()
            if file_extension not in self.allowed_extensions:
                raise HTTPException(status_code=400, detail="File type not allowed (PDF, TXT, JPG, PNG, IMG)")

            if resolved_path.stat().st_size > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File size exceeds {self.max_file_size // (1024 * 1024)} MB limit",
                )

            return str(resolved_path), resolved_path.name

        raise HTTPException(status_code=400, detail="Provide either 'file' (upload), 'file_path', or 'job_text' (raw text)")

    async def _get_job_information(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        job_data: Optional[str],
    ) -> JobPosition:
        # Determine the full description content from various inputs
        full_description_content: Optional[str] = None
        existing_job_position: Optional[JobPosition] = None

        if job_data and job_data.strip():
            try:
                # If job_data is already a structured JSON (e.g., from DB), parse it directly
                if job_data.strip().startswith("{"):
                    existing_job_position = JobPosition(**json.loads(job_data))
                    full_description_content = existing_job_position.job_description_text # Use text from existing if available
                else:
                    # If job_data is just plain text, treat it as full_description_content
                    full_description_content = job_data
            except json.JSONDecodeError as exc:
                self.logger.warning(f"Invalid JSON in job_data, treating as raw text: {str(exc)}")
                full_description_content = job_data # Fallback to raw text if JSON parsing fails

        if file and not full_description_content: # Prioritize job_data, then file
            processed_file_path, _ = await self._validate_and_get_file_path(file, None, "GetJobInfo")
            try:
                full_description_content = await run_in_threadpool(self.agent._extract_text_from_file, processed_file_path)
            except RuntimeError as e:
                self.logger.error("Error during file content extraction for uploaded file: %s", e)
                raise HTTPException(status_code=422, detail=f"Failed to extract text from uploaded file: {e}")
        elif file_path and not full_description_content: # Prioritize file, then file_path
            processed_file_path, _ = await self._validate_and_get_file_path(None, file_path, "GetJobInfo")
            try:
                full_description_content = await run_in_threadpool(self.agent._extract_text_from_file, processed_file_path)
            except RuntimeError as e:
                self.logger.error("Error during file content extraction for provided file_path: %s", e)
                raise HTTPException(status_code=422, detail=f"Failed to extract text from file at path: {e}")

        if job_text and not full_description_content: # Prioritize file_path, then job_text
            if self._is_url(job_text):
                full_description_content = await self._fetch_url_content(job_text)
            else:
                full_description_content = job_text

        if not full_description_content:
            raise HTTPException(status_code=400, detail="Provide file, file_path, job_text, or job_data containing job description text.")

        job_information: JobPosition

        # If we have an existing (potentially incomplete) JobPosition from DB, use it as base
        if existing_job_position:
            # If it has structured data, but perhaps needs refinement or full_description_text isn't set
            if not existing_job_position.title or not existing_job_position.company.name or not existing_job_position.missions: # Check for incompleteness
                self.logger.info("Existing JobPosition is incomplete, reprocessing with LLM and post-processing.")
                # Perform LLM extraction and then post-processing
                llm_extracted_job_position = await run_in_threadpool(
                    self.agent.extract_job,
                    job_text=full_description_content # Pass raw text for LLM extraction
                )
                job_information = await run_in_threadpool(
                    post_process_job_position,
                    llm_extracted_job_position, # LLM-extracted JobPosition
                    full_description_content # Original full description for rule-based refinement
                )
            else:
                self.logger.info("Existing JobPosition is structured, applying post-processing for refinement.")
                # Even if structured, apply post-processing for consistency and potential updates
                job_information = await run_in_threadpool(
                    post_process_job_position,
                    existing_job_position,
                    full_description_content # Original full description for rule-based refinement
                )
        else:
            self.logger.info("No existing JobPosition, performing LLM extraction and post-processing.")
            # Perform initial LLM extraction
            llm_extracted_job_position = await run_in_threadpool(
                self.agent.extract_job,
                job_text=full_description_content # Pass raw text for LLM extraction
            )
            job_information = await run_in_threadpool(
                post_process_job_position,
                llm_extracted_job_position, # LLM-extracted JobPosition
                full_description_content # Original full description for rule-based refinement
            )

        # Ensure job_description_text is always set in the returned JobPosition
        job_information.job_description_text = full_description_content

        return job_information

    def extract_job(
        self,
        full_description_content: str,
        tenant_id: str = "default-tenant",
        existing_job_position: Optional[JobPosition] = None,
    ) -> dict:
        self.logger.info("Starting JobService.extract_job with LLM agent")

        # Use LLM agent for initial extraction
        llm_extracted_job_position = self.agent.extract_job(job_text=full_description_content)
        # self.logger.info("LLM extracted job position: %s", llm_extracted_job_position.model_dump_json(indent=2))

        # Apply post-processing if existing_job_position is available or LLM output needs refinement
        # For now, we assume LLM output is good, but this is where `parse_job_posting` could be adapted.
        # The `parse_job_posting` function should be adapted to take a JobPosition and refine it.
        extracted_data = llm_extracted_job_position
        extracted_data.job_description_text = full_description_content
        # Avoid dumping large JSON at INFO level. Show key fields unless DEBUG is enabled.
        if self.logger.isEnabledFor(logging.DEBUG) if hasattr(self.logger, 'isEnabledFor') else False:
            # logger provided by utils.logger uses standard logging; check and log full JSON
            try:
                self.logger.debug("Job position after initial LLM extraction: %s", extracted_data.model_dump_json(indent=2))
            except Exception:
                self.logger.debug("Job position after initial LLM extraction (compact): %s | %s", extracted_data.title, getattr(extracted_data.company, 'name', None))
        else:
            # Info-level summary with key fields
            try:
                self.logger.info(
                    "Job position after initial LLM extraction: title=%s company=%s job_id=%s",
                    extracted_data.title,
                    getattr(extracted_data.company, 'name', None),
                    getattr(extracted_data, 'job_id', None),
                )
            except Exception:
                self.logger.info("Job position after initial LLM extraction: (unable to read structured fields)")

        # If existing_job_position was provided as a hint, LLM should have incorporated it.
        # If there's specific merging logic needed post-LLM, it would go here.

        # Update _get_result_folders to use new schema fields
        extraction_dir, _ = self._get_result_folders(extracted_data.company.name, extracted_data.title)
        extract_path = extraction_dir / "extraction.json"
        with open(extract_path, "w", encoding="utf-8") as handle:
            handle.write(extracted_data.model_dump_json(indent=2))

        # Save to SQLite multi-tenant jobs table
        job_id = get_background_job_manager().save_job(
            tenant_id=tenant_id,
            job_title=extracted_data.title,
            company=extracted_data.company.name,
            extracted_data_json=extracted_data.model_dump_json(),
        )
        self.logger.info(f"Job description persisted in database with job_id={{job_id}}")

        return {
            "message": "Job extraction successful",
            "job_id": job_id,
            "job_title": extracted_data.title,
            "company": extracted_data.company.name,
            "data": extracted_data.model_dump(),
            "extract_path": str(extract_path),
            "result_folder": str(extraction_dir),
        }

    async def extract_job_from_input(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        tenant_id: str = "default-tenant",
        existing_job_position: Optional[JobPosition] = None,
    ) -> dict:
        full_description_content: Optional[str] = None

        if job_text:
            if self._is_url(job_text):
                full_description_content = await self._fetch_url_content(job_text)
            else:
                full_description_content = job_text
        elif file:
                processed_file_path, _ = await self._validate_and_get_file_path(file, None, "ExtractFromInput")
                with open(processed_file_path, "r", encoding="utf-8") as f:
                    full_description_content = f.read()
        elif file_path:
                processed_file_path, _ = await self._validate_and_get_file_path(None, file_path, "ExtractFromInput")
                with open(processed_file_path, "r", encoding="utf-8") as f:
                    full_description_content = f.read()
        else:
            raise HTTPException(status_code=400, detail="Provide either 'file', 'file_path', or 'job_text'")
        
        # Call the refactored extract_job method which uses the LLM agent
        return await run_in_threadpool(
            self.extract_job,
            full_description_content=full_description_content,
            tenant_id=tenant_id,
            existing_job_position=existing_job_position,
        )

    async def analyze_job_candidate(
        self,
        file: Optional[UploadFile],
        file_path: Optional[str],
        job_text: Optional[str],
        job_data: Optional[str],
        tenant_id: str = "default-tenant",
    ) -> dict:
        # _get_job_information can now return either a JobPosition or the full_description_content (str)
        job_info_or_content = await self._get_job_information(file, file_path, job_text, job_data)

        job_information: JobPosition
        full_description_content: str

        if isinstance(job_info_or_content, JobPosition):
            job_information = job_info_or_content
            full_description_content = job_information.full_description if job_information.full_description else job_text if job_text else ""
        else: # It's a string, meaning raw full_description_content
            full_description_content = job_info_or_content
            self.logger.info("No structured job_data provided, performing LLM extraction first.")
            # Perform initial LLM extraction
            job_information = await run_in_threadpool(
                self.agent.extract_job,
                job_text=full_description_content # Pass raw text for LLM extraction
            )

        # Apply programmatic post-processing to refine the LLM-extracted (or initial JSON-parsed) JobPosition
        job_information = await run_in_threadpool(
            post_process_job_position,
            job_information, # LLM-extracted or initial JobPosition
            full_description_content # Original full description for rule-based refinement
        )

        # The LLM agent for analysis will now receive the programmatically parsed JobPosition
        candidate_analysis = await run_in_threadpool(
            self.agent.analyze_job_for_candidate,
            job_information=job_information,
            output_schema=CandidateAnalysis,
            message="Analyze this job posting from a candidate's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company.name, job_information.title) # Use new schema fields
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        candidate_analysis_path = analysis_dir / "candidate_analysis.json"
        with open(candidate_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(candidate_analysis.model_dump_json(indent=2))

        # Save Job in database
        job_id = get_background_job_manager().save_job(
            tenant_id=tenant_id,
            job_title=job_information.title,
            company=job_information.company.name,
            extracted_data_json=job_information.model_dump_json(),
        )

        return {
            "message": "Candidate analysis successful",
            "job_id": job_id,
            "job_title": job_information.title,
            "company": job_information.company.name,
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
        tenant_id: str = "default-tenant",
    ) -> dict:
        job_info_or_content = await self._get_job_information(file, file_path, job_text, job_data)

        job_information: JobPosition
        full_description_content: str

        if isinstance(job_info_or_content, JobPosition):
            job_information = job_info_or_content
            full_description_content = job_information.full_description if hasattr(job_information, 'full_description') and job_information.full_description else job_text if job_text else ""
        else: # It's a string, meaning raw full_description_content
            full_description_content = job_info_or_content
            self.logger.info("No structured job_data provided, performing LLM extraction first.")
            # Perform initial LLM extraction
            job_information = await run_in_threadpool(
                self.agent.extract_job,
                job_text=full_description_content # Pass raw text for LLM extraction
            )

        # Apply programmatic post-processing to refine the LLM-extracted (or initial JSON-parsed) JobPosition
        job_information = await run_in_threadpool(
            post_process_job_position,
            job_information, # LLM-extracted or initial JobPosition
            full_description_content # Original full description for rule-based refinement
        )

        # The LLM agent for analysis will now receive the programmatically parsed JobPosition
        recruiter_analysis = await run_in_threadpool(
            self.agent.analyze_job_for_recruiter,
            job_information=job_information,
            output_schema=RecruiterAnalysis,
            message="Analyze this job posting from a recruiter's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company.name, job_information.title) # Use new schema fields
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        recruiter_analysis_path = analysis_dir / "recruiter_analysis.json"
        with open(recruiter_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(recruiter_analysis.model_dump_json(indent=2))

        # Save Job in database
        job_id = get_background_job_manager().save_job(
            tenant_id=tenant_id,
            job_title=job_information.title,
            company=job_information.company.name,
            extracted_data_json=job_information.model_dump_json(),
        )

        return {
            "message": "Recruiter analysis successful",
            "job_id": job_id,
            "job_title": job_information.title,
            "company": job_information.company.name,
            "job_information": job_information.model_dump(),
            "recruiter_analysis": recruiter_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "recruiter_analysis_path": str(recruiter_analysis_path),
        }

    async def analyze_job(self, file: Optional[UploadFile], file_path: Optional[str], job_text: Optional[str], job_data: Optional[str], tenant_id: str = "default-tenant") -> dict:
        job_info_or_content = await self._get_job_information(file, file_path, job_text, job_data)

        job_information: JobPosition
        full_description_content: str

        if isinstance(job_info_or_content, JobPosition):
            job_information = job_info_or_content
            full_description_content = job_information.full_description if hasattr(job_information, 'full_description') and job_information.full_description else job_text if job_text else ""
        else: # It's a string, meaning raw full_description_content
            full_description_content = job_info_or_content
            self.logger.info("No structured job_data provided, performing LLM extraction first.")
            # Perform initial LLM extraction
            job_information = await run_in_threadpool(
                self.agent.extract_job,
                job_text=full_description_content # Pass raw text for LLM extraction
            )

        # Apply programmatic post-processing to refine the LLM-extracted (or initial JSON-parsed) JobPosition
        job_information = await run_in_threadpool(
            post_process_job_position,
            job_information, # LLM-extracted or initial JobPosition
            full_description_content # Original full description for rule-based refinement
        )

        # The LLM agent for analysis will now receive the programmatically parsed JobPosition
        candidate_analysis = await run_in_threadpool(
            self.agent.analyze_job_for_candidate,
            job_information=job_information,
            output_schema=CandidateAnalysis,
            message="Analyze this job posting from a candidate's perspective",
        )
        recruiter_analysis = await run_in_threadpool(
            self.agent.analyze_job_for_recruiter,
            job_information=job_information,
            output_schema=RecruiterAnalysis,
            message="Analyze this job posting from a recruiter's perspective",
        )

        extraction_dir, analysis_dir = self._get_result_folders(job_information.company.name, job_information.title) # Use new schema fields
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as handle:
            handle.write(job_information.model_dump_json(indent=2))

        candidate_analysis_path = analysis_dir / "candidate_analysis.json"
        with open(candidate_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(candidate_analysis.model_dump_json(indent=2))

        recruiter_analysis_path = analysis_dir / "recruiter_analysis.json"
        with open(recruiter_analysis_path, "w", encoding="utf-8") as handle:
            handle.write(recruiter_analysis.model_dump_json(indent=2))

        # Save Job in database
        job_id = get_background_job_manager().save_job(
            tenant_id=tenant_id,
            job_title=job_information.title,
            company=job_information.company.name,
            extracted_data_json=job_information.model_dump_json(),
        )

        return {
            "message": "Job analysis successful",
            "job_id": job_id,
            "job_title": job_information.title,
            "company": job_information.company.name,
            "job_information": job_information.model_dump(),
            "candidate_analysis": candidate_analysis.model_dump(),
            "recruiter_analysis": recruiter_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "candidate_analysis_path": str(candidate_analysis_path),
            "recruiter_analysis_path": str(recruiter_analysis_path),
        }
