"""Golden-set eval: live job extraction on the self-hosted text model (P2-06). Same opt-in as
``test_live_cv_extract.py``: ``RUN_LIVE_LLM=1 uv run pytest -m live -s -q``."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from recruitai.ai.gateway import TextPart
from recruitai.ai.prompts.jobs import PROMPT_VERSION, SYSTEM_PROMPT_JOB_EXTRACTION
from recruitai.ai.qwen import QwenGateway, build_client, build_vl_client
from recruitai.ai.usage import AiCall
from recruitai.config import AGENTS, Settings
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.jobs.schemas import JobPosition

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_LIVE_LLM=1 to call real models",
    ),
]

JD = Path(__file__).parent.parent / "fixtures" / "live" / "jd_python_paris.txt"


async def test_text_model_extracts_job(db_session):
    settings = Settings(  # type: ignore[call-arg]
        agents={a: {"provider": "qwen"} for a in AGENTS},
        ai_call_timeout_s=180.0,
        ai_daily_quota_per_user=100,
    )
    ctx = await get_org_context(
        CurrentUser(firebase_uid=f"uid-live-{uuid4().hex[:8]}", email="l@example.test"),
        db_session,
        x_org_id=None,
    )
    gateway = QwenGateway(
        client=build_client(settings),
        vl_client=build_vl_client(settings),
        settings=settings,
        db=db_session,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    job = await gateway.generate(
        schema=JobPosition,
        system=SYSTEM_PROMPT_JOB_EXTRACTION,
        parts=[TextPart(JD.read_text(encoding="utf-8"))],
        feature=PROMPT_VERSION,
    )
    row = (
        await db_session.execute(select(AiCall).where(AiCall.org_id == ctx.org_id))
    ).scalar_one()
    print(  # synthetic data only
        f"\nLIVE job: in={row.input_tokens} out={row.output_tokens} title={job.title!r} "
        f"company={job.company.name!r} contract={job.badges.contract_type!r} "
        f"location={job.badges.location!r} remote={job.badges.remote_policy!r} "
        f"missions={len(job.missions)} stack={job.tech_stack} "
        f"salary={(job.compensation.min_salary, job.compensation.max_salary) if job.compensation else None}"
    )
    assert "python" in job.title.lower()
    assert "fictiva" in job.company.name.lower()
    assert "CDI" in (job.badges.contract_type or "")
    assert len(job.missions) >= 2
    assert any("fastapi" in t.lower() for t in job.tech_stack)
    assert row.status == "ok" and row.input_tokens > 0 and row.feature == "job_extract"
