"""Golden-set eval: a live, streamed coach reply (P2-23e). Same opt-in as the other evals:
``RUN_LIVE_LLM=1 uv run pytest -m live -s -q -k coach``. Synthetic data only.

This is the only check of the real ``stream()`` of both gateways (the unit tests use mocked
clients), so it asserts what must always hold: the reply really arrives in several chunks, in
the candidate's language, grounded in the profile/job, and the turn is stored."""

import os
import re
from uuid import uuid4

import pytest

from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.coach import service
from recruitai.modules.jobs import repository as jobs_repo
from tests.evals.test_live_fit import CV, _gateway
from tests.evals.test_live_letter import JOB
from tests.integration.coach_replies import replies
from tests.unit.test_jobs_parser import blank_job

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_LIVE_LLM=1 to call real models",
    ),
]


@pytest.mark.parametrize("backend", ["gemini", "qwen"])
async def test_model_streams_a_grounded_french_coaching_reply(db_session, backend):
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
    conversation = await service.create_conversation(
        db_session, org_id=ctx.org_id, job_id=posting.id
    )
    _, gateway = _gateway(backend, db_session, ctx)

    chunks = [
        chunk
        async for chunk in replies(
            db_session,
            gateway,
            org_id=ctx.org_id,
            conversation_id=conversation.id,
            content="Quels points dois-je améliorer sur mon CV pour ce poste ?",
        )
    ]

    reply = "".join(chunks)
    print(
        f"\nLIVE coach/{backend}: chunks={len(chunks)} chars={len(reply)}\n{reply}"
    )  # synthetic
    assert len(chunks) > 1, "the reply did not arrive incrementally"
    assert len(reply) > 100
    assert re.search(r"\b(vous|votre|vos|je|les|des|pour)\b", reply.lower())  # French
    assert "dear " not in reply.lower()
    assert any(k in reply for k in ("Python", "Flask", "React", "SQL", "Docker")), (
        "the reply never mentions anything from the profile or the job"
    )
    stored = await service.list_messages(
        db_session, org_id=ctx.org_id, conversation_id=conversation.id
    )
    assert [m.role for m in stored] == ["user", "assistant"] and stored[
        1
    ].content == reply.strip()


async def test_model_uses_tools_and_web_research_and_keeps_pii_out_of_queries(
    db_session,
):
    """Live, Vertex only: the loop reads the job, searches the web about the (public) company,
    and the queries carry nothing of the candidate. Synthetic CV and job."""
    from recruitai.ai import gemini
    from recruitai.ai.gateway import ToolCall  # noqa: F401
    from recruitai.ai.text import compact_json  # noqa: F401
    from recruitai.config import AGENTS, Settings
    from tests.integration.coach_replies import events

    settings = Settings(  # type: ignore[call-arg]
        google_genai_use_vertexai=True,
        agents={a: {"provider": "gemini", "model": "gemini-3.8-flash"} for a in AGENTS},
        ai_call_timeout_s=120.0,
        ai_daily_quota_per_user=100,
        coach_job_focus=True,
    )
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
    conversation = await service.create_conversation(
        db_session, org_id=ctx.org_id, job_id=posting.id
    )
    llm = gemini.GeminiGateway(
        client=gemini.build_client(settings),
        settings=settings,
        db=db_session,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )

    got = [
        e
        async for e in events(
            db_session,
            llm,
            org_id=ctx.org_id,
            conversation_id=conversation.id,
            content="Que dois-je savoir sur cette entreprise et comment me préparer à l'entretien ?",
            settings=settings,
        )
    ]

    names = [n for n, _ in got]
    steps = [d["label"] for n, d in got if n == "step" and d["status"] == "done"]
    reply = "".join(d["text"] for n, d in got if n == "token")
    stored = await service.list_messages(
        db_session, org_id=ctx.org_id, conversation_id=conversation.id
    )
    meta = stored[1].meta
    print(
        f"\nLIVE coach loop: events={names}\nsteps={steps}\nqueries={meta['queries']}\n{reply[:600]}"
    )
    assert names[0] == "context" and names[-1] == "done"
    assert len(reply) > 200
    assert any(q for q in meta["queries"]) or steps, "the model used no tool at all"
    assert not any("Martel" in q or "@" in q for q in meta["queries"]), (
        "personal data in a search query"
    )
