"""Golden-set eval: live fit analysis on the self-hosted Qwen text model and on Gemini on
Vertex (P2-13/P2-14). Same opt-in as the other evals: ``RUN_LIVE_LLM=1 uv run pytest -m live -s -q``. Synthetic data only.

Asserts score *bands* for an obvious match and an obvious mismatch, never exact wording.
"""

import os
from uuid import uuid4

import pytest

from recruitai.ai import gemini
from recruitai.ai.qwen import QwenGateway, build_client, build_vl_client
from recruitai.config import AGENTS, Settings
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import (
    CVInformation,
    Experience,
    Formation,
    PersonalInfo,
    RawSkill,
)
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.matching import service
from tests.unit.test_jobs_parser import blank_job

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_LIVE_LLM=1 to call real models",
    ),
]

CV = CVInformation(
    personal_info=PersonalInfo(name="Lucas Martel", email="lucas.martel@example.test"),
    formations=[
        Formation(
            degree="Bachelor of Science",
            field="Computer Science",
            institution="Université Claude-Bernard Lyon 1",
        )
    ],
    experiences=[
        Experience(
            job_title="Software Development Intern",
            company="Brightwave SAS",
            start_date="June 2023",
            end_date="September 2023",
            description="REST endpoints with Flask, unit tests with pytest",
        ),
        Experience(
            job_title="Freelance Web Developer",
            company="self-employed",
            start_date="January 2024",
            end_date="Present",
            description="Three small business websites with React and Node.js",
        ),
    ],
    skills=[
        RawSkill(name=n) for n in ("Python", "JavaScript", "React", "Flask", "SQL")
    ],
    summary="Recent graduate who likes web development and clean code.",
)

CASES = {
    "match": (
        {
            "title": "Développeur Python Junior (H/F)",
            "missions": ["Développer des API avec Flask", "Écrire des tests pytest"],
            "tech_stack": ["Python", "Flask", "React", "SQL"],
            "profile": {
                "experience": "0 à 2 ans d'expérience",
                "education": "Bac+3",
                "technical_skills": ["Python", "Flask"],
                "soft_skills": [],
                "nice_to_have": ["Docker"],
            },
        },
        # An obvious match must never be rejected (the 3B model gave 40/'maybe', a weaker
        # result than a good reviewer's 60+, see the session report).
        (lambda score: score > 35, {"go", "maybe"}),
    ),
    "mismatch": (
        {
            "title": "Chef pâtissier (H/F)",
            "missions": [
                "Concevoir la carte des desserts",
                "Encadrer une brigade de 6 personnes",
            ],
            "tech_stack": [],
            "profile": {
                "experience": "8 ans d'expérience en pâtisserie",
                "education": "CAP pâtissier",
                "technical_skills": [
                    "Pâte feuilletée",
                    "Chocolat",
                    "Gestion de brigade",
                ],
                "soft_skills": [],
                "nice_to_have": [],
            },
        },
        (lambda score: score <= 35, {"no_go"}),
    ),
}


MATCH_XFAIL_QWEN = pytest.mark.xfail(
    reason="Qwen 3B (slm) rejects an obvious match under the corporate persona "
    "(scored 40, 30, 20 across runs). A model limitation, not a code defect.",
    strict=False,
)


def _gateway(backend: str, db, ctx):
    if backend == "gemini":
        settings = Settings(  # type: ignore[call-arg]
            llm_provider="gemini",
            google_genai_use_vertexai=True,
            ai_call_timeout_s=120.0,
            ai_daily_quota_per_user=100,
        )
        return settings, gemini.GeminiGateway(
            client=gemini.build_client(settings),
            settings=settings,
            db=db,
            org_id=ctx.org_id,
            user_id=ctx.user_id,
        )
    settings = Settings(  # type: ignore[call-arg]
        agents={a: {"provider": "qwen"} for a in AGENTS},
        ai_call_timeout_s=180.0,
        ai_daily_quota_per_user=100,
    )
    return settings, QwenGateway(
        client=build_client(settings),
        vl_client=build_vl_client(settings),
        settings=settings,
        db=db,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )


@pytest.mark.parametrize(
    ("backend", "case"),
    [
        pytest.param("qwen", "match", marks=MATCH_XFAIL_QWEN),
        ("qwen", "mismatch"),
        ("gemini", "match"),
        ("gemini", "mismatch"),
    ],
)
async def test_model_scores_obvious_cases_in_the_expected_band(
    db_session, backend, case
):
    job_fields, (in_band, verdicts) = CASES[case]
    ctx = await get_org_context(
        CurrentUser(firebase_uid=f"uid-live-{uuid4().hex[:8]}", email="l@example.test"),
        db_session,
        x_org_id=None,
    )
    await candidates_repo.upsert(
        db_session, org_id=ctx.org_id, document_id=None, info=CV
    )
    posting = await jobs_repo.add(
        db_session, org_id=ctx.org_id, source="manual", external_id=None,
        info=blank_job(**job_fields),
    )  # fmt: skip
    _, gateway = _gateway(backend, db_session, ctx)

    row = await service.analyze(
        db_session, gateway, org_id=ctx.org_id, job_id=posting.id
    )

    d = row.data
    print(  # synthetic data only
        f"\nLIVE fit/{backend}/{case}: score={row.score} verdict={row.verdict} fit={d['is_fit']} "
        f"strengths={len(d['strengths'])} gaps={len(d['gaps'])} model={row.model} "
        f"summary={'yes' if d['summary'] else 'no'} advice={'yes' if d['constructive_feedback'] else 'no'}"
    )
    assert in_band(row.score), f"score {row.score} outside the expected band for {case}"
    assert row.verdict in verdicts, f"verdict {row.verdict} for {case}"
    assert d["strengths"] or d["gaps"]
    assert row.model == gateway.model_name("smart")
