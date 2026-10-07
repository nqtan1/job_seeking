"""The Procrastinate worker with the two things that cost money or leave the machine replaced, for
browser tests of the job radar: a scripted model (fit scores 86, 38, 74, ...) and a France Travail
stand-in with three offers.

    uv run procrastinate --app=tests.e2e_worker.app worker
"""

import itertools
from pathlib import Path
from typing import Any

from recruitai.ai import dependencies
from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.errors import UpstreamUnavailable
from recruitai.modules.jobs.providers import factory
from recruitai.modules.matching.schemas import FitCheck
from recruitai.worker import app  # noqa: F401  (the CLI reads ``app``)
from tests.e2e_radar_fakes import Provider

FAIL_FLAG = Path(".e2e-run/fail-ai")
SCORES = itertools.cycle([86, 38, 74])


class ScriptedFit(FakeLLMGateway):
    async def generate(self, *, schema: type, **_: object) -> Any:  # type: ignore[override]
        if (
            FAIL_FLAG.exists()
        ):  # a browser test switches the AI "off" by creating this file
            raise UpstreamUnavailable(
                "The AI provider is unavailable.", code="ai_unavailable"
            )
        score = next(SCORES)
        weak = score < 70
        return FitCheck.model_validate(
            {
                "is_fit": not weak,
                "fit_score": score,
                "recommendation": "no_go" if weak else "go",
                "strengths": []
                if weak
                else ["Python and FastAPI experience", "PostgreSQL in production"],
                "gaps": ["No cloud certification"],
                "reasons": ["Scripted for the browser test"],
                "key_missing_requirements": ["Kubernetes"] if score != 86 else [],
                "confidence": 0.8,
                "summary": "Scripted.",
                "constructive_feedback": "Mention your FastAPI services.",
            }
        )


_llm = ScriptedFit()
dependencies.build_llm_gateway = lambda *a, **k: _llm  # type: ignore[assignment]
factory.france_travail_provider = lambda: Provider()  # type: ignore[assignment]
