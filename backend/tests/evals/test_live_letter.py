"""Golden-set eval: live letter generation (P2-23). Same opt-in as the other evals:
``RUN_LIVE_LLM=1 uv run pytest -m live -s -q -k letter``. Synthetic data only.

Asserts what must always hold, never exact wording: French, no template placeholders or
markdown, the programmatic blocks come from the data, a believable length, and nothing the
profile doesn't support (checked with the module's own grounding check)."""

import os
import re
from uuid import uuid4

import pytest

from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.letters import quality, service
from recruitai.modules.letters.schemas import LetterContent
from tests.evals.test_live_fit import CV, _gateway
from tests.unit.test_jobs_parser import blank_job

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_LIVE_LLM=1 to call real models",
    ),
]

JOB = {
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
}


@pytest.mark.parametrize("backend", ["gemini", "qwen"])
async def test_model_writes_a_grounded_french_letter(db_session, backend):
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
        info=blank_job(**JOB),
    )  # fmt: skip
    _, gateway = _gateway(backend, db_session, ctx)

    letter = await service.generate(
        db_session,
        gateway,
        org_id=ctx.org_id,
        job_id=posting.id,
        language="fr",
        tone="professional",
    )

    content = LetterContent.model_validate(letter.content)
    prose = "\n".join(
        [
            content.subject,
            content.salutation,
            content.opening,
            *content.body,
            content.closing,
        ]
    )
    panel = quality.check(
        content,
        CV.model_dump(mode="json"),
        blank_job(**JOB).model_dump(mode="json"),
        "standard",
    )
    print(  # synthetic data only: lets a human judge the writing, not just the checks
        f"\nLIVE letter/{backend}: words={panel.quality.word_count} "
        f"claims={[(c.kind, c.term) for c in panel.unsupported_claims]} "
        f"cliches={panel.quality.cliches} coverage={panel.quality.keyword_coverage.ratio}\n{prose}"
    )
    assert content.header.name == "Lucas Martel" and content.recipient.company == "Acme"
    assert content.signature == "Lucas Martel"  # from the profile, not the model
    assert content.subject and content.salutation and len(content.body) >= 2
    assert not re.search(r"\[[^\]]+\]", prose), (
        "template placeholder left in the letter"
    )
    assert not re.search(r"\*\*|```|^#", prose, re.MULTILINE), "markdown in the letter"
    assert "Lucas Martel" not in content.closing  # the signature is added by code
    assert (
        re.search(r"\b(je|j')", prose.lower()) and "dear" not in prose.lower()
    )  # French
    assert 125 <= panel.quality.word_count <= 375  # standard = about 250 words
    assert [c for c in panel.unsupported_claims if c.kind in ("skill", "number")] == []
