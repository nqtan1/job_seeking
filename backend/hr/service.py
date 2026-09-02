from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from core.auth import TenantContext
from fastapi import HTTPException
from hr.agent import HRRankingAgent
from hr.schema import HRBatchRankingRequest, HRBatchRankingResult
from utils.logger import get_logger


class HRRankingService:
    def __init__(self, agent: HRRankingAgent, logger_name: str = "hr.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="hr_api.log", level="INFO")
        self.result_base_dir = Path(__file__).resolve().parent.parent / "db/hr/runs"
        self.result_base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^a-zA-Z0-9_-]", "", text.replace(" ", "_"))
        return text[:80].rstrip("_")

    def _get_result_folder(self, request: HRBatchRankingRequest, tenant_context: TenantContext) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        company = self._sanitize_filename(request.job_information.company or "company")
        job_title = self._sanitize_filename(request.job_information.job_title or "job")
        tenant_id = self._sanitize_filename(tenant_context.tenant_id or "tenant")
        folder_name = f"{timestamp}_{tenant_id}_{company}_{job_title}"
        result_dir = self.result_base_dir / folder_name
        result_dir.mkdir(parents=True, exist_ok=True)
        return result_dir

    def rank_candidates(
        self,
        request: HRBatchRankingRequest,
        tenant_context: TenantContext,
    ) -> HRBatchRankingResult:
        if not request.candidates:
            raise HTTPException(status_code=400, detail="At least one candidate is required")

        self.logger.info(
            "Starting HR batch ranking tenant=%s company=%s candidates=%s",
            tenant_context.tenant_id,
            request.job_information.company,
            len(request.candidates),
        )

        ranked_candidates = self.agent.rank_candidates(request)
        result_folder = self._get_result_folder(request, tenant_context)

        ranking_path = result_folder / "ranking.json"
        generated_at = datetime.now()
        with open(ranking_path, "w", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "tenant_id": tenant_context.tenant_id,
                        "company_type": request.company_type,
                        "job_information": request.job_information.model_dump(),
                        "ranked_candidates": [candidate.model_dump() for candidate in ranked_candidates],
                        "generated_at": generated_at.isoformat(),
                        "shortlist_size": request.shortlist_size,
                        "recruiter_attend": request.recruiter_attend,
                        "custom_context": request.custom_context,
                    },
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

        request_path = result_folder / "request.json"
        with open(request_path, "w", encoding="utf-8") as file:
            json.dump(request.model_dump(), file, indent=2, ensure_ascii=False, default=str)

        shortlisted_count = sum(1 for candidate in ranked_candidates if candidate.shortlisted)
        top_candidate = ranked_candidates[0] if ranked_candidates else None
        summary = (
            f"Top candidate: {top_candidate.candidate_name} with score {top_candidate.fit_score}. "
            f"Shortlisted {shortlisted_count} of {len(ranked_candidates)} candidates."
            if top_candidate
            else "No candidates ranked."
        )

        return HRBatchRankingResult(
            message="HR batch ranking successful",
            tenant_id=tenant_context.tenant_id,
            company_type=request.company_type,
            job_title=request.job_information.job_title,
            company=request.job_information.company,
            total_candidates=len(ranked_candidates),
            shortlisted_count=shortlisted_count,
            summary=summary,
            ranked_candidates=ranked_candidates,
            result_folder=str(result_folder),
            ranking_path=str(ranking_path),
            request_path=str(request_path),
            generated_at=generated_at,
        )