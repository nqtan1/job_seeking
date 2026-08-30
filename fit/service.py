from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from fit.agent import FitAgent
from fit.schema import FitAnalysisRequest, FitAnalysisResponse, FitCheck
from utils.logger import get_logger


class FitService:
    def __init__(self, agent: FitAgent, logger_name: str = "fit.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="fit_api.log", level="INFO")
        self.result_base_dir = Path(__file__).resolve().parent.parent / "db/fit/analyze"
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

    async def analyze_fit(self, request: FitAnalysisRequest) -> FitAnalysisResponse:
        self.logger.info(
            "Persisting fit analysis candidate=%s company=%s company_type=%s",
            request.candidate_cv.personal_info.name,
            request.job_information.company,
            request.company_type,
        )

        fit_check = self.agent.analyze_fit(
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

        return FitAnalysisResponse(
            message="Fit analysis successful",
            company_type=request.company_type,
            fit_check=fit_check,
            result_folder=str(result_folder),
            analysis_path=str(analysis_path),
            request_path=str(request_path),
        )