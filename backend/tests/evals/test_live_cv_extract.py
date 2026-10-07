"""Golden-set eval (ARCHITECTURE §4.5): live CV extraction against the owner's self-hosted
Qwen servers (text model + vision model).

Opt-in: ``RUN_LIVE_LLM=1 uv run pytest -m live -s -q`` (``-s`` prints the per-call stats used
for the model comparison). Synthetic fixtures only (``tests/fixtures/live``). Config comes
from ``Settings`` (``.env``); nothing from it is printed. Costs one real model call per case.
"""

import io
import os
import textwrap
import time
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from recruitai.ai.gateway import FilePart, TextPart
from recruitai.ai.prompts.cv_extract import PROMPT_VERSION, SYSTEM_PROMPT
from recruitai.ai.qwen import QwenGateway, build_client, build_vl_client
from recruitai.ai.usage import AiCall
from recruitai.config import AGENTS, Settings
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates.schemas import CVInformation
from recruitai.modules.candidates.service import _DATA_NOTICE

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_LIVE_LLM=1 to call real models",
    ),
]

FIXTURES = Path(__file__).parent.parent / "fixtures" / "live"
# name fragment, email, a skill that must be found, minimum experiences
EXPECTED = {
    "junior_dev": ("Martel", "lucas.martel@example.test", "python", 2),
    "senior_career_change": ("Dubois", "marieclaire.dubois@example.test", "sql", 2),
    "french_cv": ("Bernard", "thomas.bernard@example.test", "java", 2),
}
MINIMIZED = {"photo", "date_of_birth", "birth_date", "dob", "nationality", "gender"}


def _png(text: str) -> bytes:
    """Render the fixture as an image, so the vision model gets a CV it has to read."""
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    lines = [w for line in text.splitlines() for w in (textwrap.wrap(line, 90) or [""])]
    img = Image.new("RGB", (1000, 28 * len(lines) + 40), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((20, 20 + 28 * i), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def _run(
    db_session, cv: str, as_image: bool
) -> tuple[CVInformation, AiCall, float]:
    settings = Settings(  # type: ignore[call-arg]
        agents={a: {"provider": "qwen"} for a in AGENTS},
        ai_call_timeout_s=180.0,
        ai_daily_quota_per_user=100,
    )
    if as_image and not settings.qwen_vl_base_url:
        pytest.skip("QWEN_VL_BASE_URL is not configured")
    ctx = await get_org_context(
        CurrentUser(
            firebase_uid=f"uid-live-{uuid4().hex[:8]}", email="live@example.test"
        ),
        db_session,
        x_org_id=None,
    )
    text = (FIXTURES / f"{cv}.txt").read_text(encoding="utf-8")
    file_part = (
        FilePart(data=_png(text), mime_type="image/png")
        if as_image
        else FilePart(data=text.encode(), mime_type="text/plain")
    )
    gateway = QwenGateway(
        client=build_client(settings),
        vl_client=build_vl_client(settings),
        settings=settings,
        db=db_session,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    started = time.perf_counter()
    info = await gateway.generate(
        schema=CVInformation,
        system=SYSTEM_PROMPT,
        parts=[TextPart(_DATA_NOTICE), file_part],
        feature=PROMPT_VERSION,
    )
    elapsed = time.perf_counter() - started
    row = (
        await db_session.execute(select(AiCall).where(AiCall.org_id == ctx.org_id))
    ).scalar_one()
    return info, row, elapsed


def _check(info: CVInformation, row: AiCall, cv: str) -> None:
    print(  # synthetic data only: lets a human judge quality, not just validity
        f"  exp={[(e.job_title, e.start_date, e.end_date) for e in info.experiences]}"
        f" edu={[(f.degree, f.field) for f in info.formations]}"
        f" skills={len(info.skills)} phone={info.personal_info.phone!r}"
    )
    name, email, skill, min_exp = EXPECTED[cv]
    assert name.lower() in info.personal_info.name.lower()
    assert (info.personal_info.email or "").lower() == email
    assert len(info.experiences) >= min_exp
    assert all(e.start_date for e in info.experiences)  # every fixture states its dates
    assert info.formations
    assert any(skill in s.name.lower() for s in info.skills)
    assert not MINIMIZED & set(info.model_dump())
    assert not MINIMIZED & set(info.personal_info.model_dump())
    # ai_calls: metadata only, never CV content
    assert row.status == "ok" and row.input_tokens > 0 and row.output_tokens > 0
    assert row.feature == "cv_extract" and row.prompt_version == PROMPT_VERSION
    assert (
        name.lower()
        not in " ".join(
            str(v) for v in (row.feature, row.model, row.prompt_version)
        ).lower()
    )


@pytest.mark.parametrize("cv", list(EXPECTED))
async def test_text_model_extracts_cv(db_session, cv):
    info, row, elapsed = await _run(db_session, cv, as_image=False)
    print(
        f"\nLIVE text/{cv}: {elapsed:.1f}s in={row.input_tokens} out={row.output_tokens}"
    )
    _check(info, row, cv)


@pytest.mark.parametrize("cv", ["junior_dev", "french_cv"])
async def test_vision_model_extracts_cv(db_session, cv):
    info, row, elapsed = await _run(db_session, cv, as_image=True)
    print(
        f"\nLIVE image/{cv}: {elapsed:.1f}s in={row.input_tokens} out={row.output_tokens}"
    )
    _check(info, row, cv)
