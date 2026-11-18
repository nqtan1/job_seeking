"""The Procrastinate worker with the two things that cost money or leave the machine replaced, for
browser tests of the job radar: a scripted model (fit scores 86, 38, 74, ...) and a France Travail
stand-in with three offers.

    uv run procrastinate --app=tests.e2e_worker.app worker
"""

# Set before recruitai is imported: it reads its Settings once, at import time (worker.py).
import os

# The isolated stack has no .env: switch on the features the browser tests cover.
for _flag in ("HELPERS_ENABLED", "CV_REVIEW_ENABLED"):
    os.environ.setdefault(_flag, "true")

import itertools
import json
from pathlib import Path
from typing import Any

from recruitai.ai import dependencies
from recruitai.ai.gateway import FakeLLMGateway, Part, TextPart
from recruitai.core.errors import UpstreamUnavailable
from recruitai.modules.agents.helpers.runner import TextResult
from recruitai.modules.cvreview.schemas import (
    BlockComment,
    LlmDimension,
    LlmReview,
    LlmSummary,
    Quote,
)
from recruitai.modules.jobs.providers import factory
from recruitai.modules.matching.schemas import FitCheck
from recruitai.worker import app  # noqa: F401  (the CLI reads ``app``)
from tests.e2e_radar_fakes import Provider

FAIL_FLAG = Path(".e2e-run/fail-ai")
SCORES = itertools.cycle([86, 38, 74])


def cv_review(parts: tuple[Part, ...] | list[Part]) -> LlmReview:
    """A "poor" comment on every non-heading line, quoting its first words (so it is grounded
    and its highlight shows on the PDF)."""
    text = "".join(p.text for p in parts if isinstance(p, TextPart))
    listing = text.split("<cv_blocks>")[1].split("</cv_blocks>")[0]
    blocks = [b for b in json.loads(listing) if b["kind"] != "heading"]
    dim = LlmDimension(
        reason="Scripted.", block_ids=[b["id"] for b in blocks], score=60
    )
    return LlmReview(
        comments=[
            BlockComment(
                block_id=b["id"],
                criterion="impact.metric",
                citations=[Quote(block_id=b["id"], quote=b["text"][:20])],
                why="No number shows the result.",
                improve="Add one measurable result.",
                rewrite=None,
                rating="poor",
            )
            for b in blocks
        ],
        summary=LlmSummary(strengths=[], top_fixes=[b["id"] for b in blocks[:2]]),
        scope=dim,
        stack=dim,
        projects=dim,
        progression=dim,
    )


class ScriptedFit(FakeLLMGateway):
    async def generate(  # type: ignore[override]
        self, *, schema: type, parts: tuple[Part, ...] | list[Part] = (), **_: object
    ) -> Any:
        if (
            FAIL_FLAG.exists()
        ):  # a browser test switches the AI "off" by creating this file
            raise UpstreamUnavailable(
                "The AI provider is unavailable.", code="ai_unavailable"
            )
        if (
            schema is TextResult
        ):  # a helper step in a flow (browser test of the helpers)
            return TextResult(text="A canned helper answer.")
        if schema is LlmReview:  # the CV review (browser test of the PDF highlight)
            return cv_review(parts)
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
