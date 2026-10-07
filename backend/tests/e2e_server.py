"""The real API on the real DB, worker queue and Firebase emulator, with the two things that
cost money or leave the machine replaced: the LLM (canned answers per schema, so the browser
journey is deterministic) and France Travail. ``E2E_LIVE_LLM=1`` skips the fake LLM.

    uv run uvicorn tests.e2e_server:app --port 8000
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.main import create_app
from recruitai.modules.candidates.schemas import (
    CVInformation,
    Experience,
    Formation,
    PersonalInfo,
    RawSkill,
)
from recruitai.modules.jobs.router import get_job_provider
from recruitai.modules.jobs.schemas import JobPosition
from recruitai.modules.letters.schemas import BlockText, LetterDraft
from recruitai.modules.matching.schemas import FitCheck
from recruitai.modules.radar.router import get_provider as get_radar_provider
from tests.e2e_radar_fakes import Provider as RadarProvider
from tests.fixtures.jobs import FakeJobProvider

CANNED: dict[str, Any] = {
    "CVInformation": CVInformation(
        personal_info=PersonalInfo(name="Ada Lovelace", email="ada@example.test"),
        formations=[
            Formation(degree="Master", field="Informatique", institution="Paris-Saclay")
        ],
        experiences=[
            Experience(
                job_title="Senior Python Engineer",
                company="Acme Corp",
                start_date="Jan 2021",
                end_date="Present",
                description="Built FastAPI services with PostgreSQL and Docker.",
            )
        ],
        skills=[RawSkill(name="Python"), RawSkill(name="FastAPI")],
        summary="Backend engineer.",
    ),
    "JobPosition": JobPosition.model_validate(
        {
            "title": "Développeur Python Backend",
            "company": {"name": "Fictiva Logiciels"},
            "badges": {},
            "about_company": {},
            "missions": ["Build APIs"],
            "tech_stack": ["Python", "FastAPI"],
            "working_methods": [],
            "profile": {
                "experience": "3 ans",
                "education": "Bac+5",
                "technical_skills": ["Python"],
                "soft_skills": [],
                "nice_to_have": [],
            },
            "modalities": {},
            "source_meta": {},
        }
    ),
    "FitCheck": FitCheck.model_validate(
        {
            "is_fit": True,
            "fit_score": 82,
            "recommendation": "go",
            "strengths": ["Python and FastAPI experience"],
            "gaps": ["No Kubernetes"],
            "reasons": ["Strong stack match"],
            "key_missing_requirements": [],
            "confidence": 0.8,
            "summary": "A solid match.",
            "constructive_feedback": "Mention your FastAPI services.",
        }
    ),
    "LetterDraft": LetterDraft(
        subject="Candidature Développeur Python Backend",
        salutation="Madame, Monsieur,",
        opening="Je vous écris pour candidater au poste de développeur Python.",
        body=[
            "Chez Acme Corp, j'ai construit des services FastAPI.",
            "Je souhaite rejoindre Fictiva Logiciels.",
        ],
        closing="Veuillez agréer mes salutations distinguées.",
    ),
    "BlockText": BlockText(text="Un texte réécrit."),
}


class CannedLLMGateway(FakeLLMGateway):
    async def generate(self, *, schema: type, **_: object) -> Any:  # type: ignore[override]
        return CANNED[schema.__name__]

    async def stream(self, **_: object) -> AsyncGenerator[str]:  # type: ignore[override]
        for chunk in ("Votre ", "profil ", "est solide."):
            yield chunk


def build_app() -> FastAPI:
    app = create_app()
    app.dependency_overrides[verify_app_check] = lambda: None
    app.dependency_overrides[get_job_provider] = lambda: FakeJobProvider()
    app.dependency_overrides[get_radar_provider] = lambda: RadarProvider()
    if os.environ.get("E2E_LIVE_LLM") != "1":
        app.dependency_overrides[get_llm_gateway] = lambda: CannedLLMGateway()
    return app


app = build_app()
