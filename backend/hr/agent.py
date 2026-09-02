from __future__ import annotations

from typing import List, Optional

from fit.agent import FitAgent
from fit.schema import FitCheck
from hr.schema import HRBatchRankingRequest, HRCandidateInput, RankedCandidate


class HRRankingAgent:
    def __init__(self, fit_agent: FitAgent):
        self.fit_agent = fit_agent

    def _rank_candidate(
        self,
        candidate: HRCandidateInput,
        request: HRBatchRankingRequest,
    ) -> FitCheck:
        return self.fit_agent.analyze_fit(
            candidate_cv=candidate.candidate_cv,
            job_information=request.job_information,
            company_type=request.company_type,
            recruiter_attend=request.recruiter_attend,
            custom_context=candidate.custom_context or request.custom_context,
            output_schema=FitCheck,
        )

    def rank_candidates(self, request: HRBatchRankingRequest) -> List[RankedCandidate]:
        ranked_candidates: List[RankedCandidate] = []

        for candidate in request.candidates:
            fit_check = self._rank_candidate(candidate, request)
            ranked_candidates.append(
                RankedCandidate(
                    candidate_id=candidate.candidate_id,
                    candidate_name=candidate.candidate_cv.personal_info.name,
                    rank_position=0,
                    fit_score=fit_check.fit_score,
                    shortlisted=False,
                    fit_check=fit_check,
                )
            )

        ranked_candidates.sort(
            key=lambda item: (
                item.fit_score,
                item.fit_check.confidence or 0.0,
                item.candidate_name.lower(),
            ),
            reverse=True,
        )

        for index, ranked_candidate in enumerate(ranked_candidates, start=1):
            ranked_candidate.rank_position = index
            ranked_candidate.shortlisted = index <= request.shortlist_size

        return ranked_candidates