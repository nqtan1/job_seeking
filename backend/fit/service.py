from __future__ import annotations

import json
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from fit.agent import FitAgent
from fit.schema import FitAnalysisRequest, FitAnalysisResponse, FitCheck
from utils.logger import get_logger
from workers.background import get_background_job_manager


class FitService:
    def __init__(self, agent: FitAgent, logger_name: str = "fit.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="fit_api.log", level="INFO")
        self.result_base_dir = Path(tempfile.gettempdir()) / "job_seeking_db/fit/analyze"
        self.result_base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^a-zA-Z0-9_-]", "", text.replace(" ", "_"))
        return text[:80].rstrip("_")

    def _get_result_folder(self, request: FitAnalysisRequest) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        candidate_name = self._sanitize_filename(request.candidate_cv.personal_info.name or "candidate")
        job_title = self._sanitize_filename(request.job_information.job_title or "job")
        company = self._sanitize_filename(request.job_information.company or "company")
        folder_name = f"{timestamp}_{request.company_type}_{company}_{job_title}_{candidate_name}"
        result_dir = self.result_base_dir / folder_name
        result_dir.mkdir(parents=True, exist_ok=True)
        return result_dir

    async def analyze_fit(self, request: FitAnalysisRequest, tenant_id: str = "default-tenant") -> FitAnalysisResponse:
        self.logger.info(
            "Persisting fit analysis candidate=%s company=%s company_type=%s",
            request.candidate_cv.personal_info.name,
            request.job_information.company,
            request.company_type,
        )

        from starlette.concurrency import run_in_threadpool

        fit_check = await run_in_threadpool(
            self.agent.analyze_fit,
            candidate_cv=request.candidate_cv,
            job_information=request.job_information,
            company_type=request.company_type,
            recruiter_attend=request.recruiter_attend,
            custom_context=request.custom_context,
            output_schema=FitCheck,
        )

        result_folder = self._get_result_folder(request)
        analysis_path = result_folder / "fit_check.json"
        with open(analysis_path, "w", encoding="utf-8") as file:
            file.write(fit_check.model_dump_json(indent=2))

        request_path = result_folder / "request.json"
        with open(request_path, "w", encoding="utf-8") as file:
            json.dump(request.model_dump(), file, indent=2, ensure_ascii=False, default=str)

        # 1. Save Candidate structured profile to SQLite
        email = str(request.candidate_cv.personal_info.email) if request.candidate_cv.personal_info.email else None
        phone = request.candidate_cv.personal_info.phone if request.candidate_cv.personal_info.phone else None
        candidate_id = get_background_job_manager().save_candidate(
            tenant_id=tenant_id,
            name=request.candidate_cv.personal_info.name or "Unknown",
            email=email,
            phone=phone,
            extracted_data_json=request.candidate_cv.model_dump_json(),
        )

        # 2. Save Job structured description to SQLite
        job_id = get_background_job_manager().save_job(
            tenant_id=tenant_id,
            job_title=request.job_information.job_title or "Unknown",
            company=request.job_information.company or "Unknown",
            extracted_data_json=request.job_information.model_dump_json(),
        )

        # 3. Save Fit Analysis results to SQLite
        analysis_id = get_background_job_manager().save_fit_analysis(
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            job_id=job_id,
            fit_score=int(fit_check.fit_score),
            fit_data_json=fit_check.model_dump_json(),
        )
        self.logger.info(f"Fit analysis persisted in SQLite with analysis_id={analysis_id}")

        # 4. Generate Interview Kit if fit is GO or MAYBE
        interview_kit = None
        if fit_check.recommendation.value in {"go", "maybe"}:
            self.logger.info("Recommendation is %s. Generating Mock Interview Preparation Kit.", fit_check.recommendation.value)
            try:
                from starlette.concurrency import run_in_threadpool
                interview_kit = await run_in_threadpool(
                    self.agent.generate_interview_kit,
                    candidate_cv=request.candidate_cv,
                    job_information=request.job_information,
                    company_type=request.company_type,
                    custom_context=request.custom_context,
                )
            except Exception as e:
                self.logger.error("Failed to generate interview kit: %s", str(e), exc_info=True)

        return FitAnalysisResponse(
            message="Fit analysis successful",
            company_type=request.company_type,
            fit_check=fit_check,
            result_folder=str(result_folder),
            analysis_path=str(analysis_path),
            request_path=str(request_path),
            interview_kit=interview_kit,
        )