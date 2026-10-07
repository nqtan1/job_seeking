"""Fill an org with a little data from EVERY module, each piece stamped with the org's tag.

Used by the privacy tests: the export must contain all of it for its owner and none of it for
anyone else; deletion must remove all of it. Plain helper (not a pytest fixture)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts import coach as coach_prompt
from recruitai.ai.prompts import fit as fit_prompt
from recruitai.ai.prompts import letters as letters_prompt
from recruitai.core.storage import LocalStorage
from recruitai.core.tasks import TaskRun
from recruitai.modules.applications import service as applications
from recruitai.modules.applications.schemas import ApplicationIn
from recruitai.modules.coach import service as coach
from recruitai.modules.documents import service as documents
from recruitai.modules.identity.models import Membership, Organization, User
from recruitai.modules.letters import service as letters
from recruitai.modules.letters.schemas import LetterDraft
from recruitai.modules.matching import service as matching
from recruitai.modules.matching.schemas import FitCheck
from tests.integration.test_letters_service import _tenant
from tests.unit.test_schemas import VALID


@dataclass
class OrgData:
    org: Organization
    user: User
    tag: str
    document_keys: list[str]
    org_id: UUID  # plain values: ORM attributes expire on rollback, these do not
    user_id: UUID


async def seed_org(
    db: AsyncSession, tag: str, *, llm: FakeLLMGateway, storage: LocalStorage
) -> OrgData:
    org, job = await _tenant(db, tag)
    user = (
        await db.execute(select(User).where(User.firebase_uid == f"fb-{tag}"))
    ).scalar_one()
    db.add(
        Membership(org_id=org.id, user_id=user.id, role="owner")
    )  # as a real sign-up does
    await db.flush()

    cv = await documents.upload(
        db,
        storage,
        org_id=org.id,
        uploaded_by=user.id,
        kind="cv",
        data=f"%PDF-1.4 cv-{tag}".encode(),
    )
    jd = await documents.upload(
        db,
        storage,
        org_id=org.id,
        uploaded_by=user.id,
        kind="jd",
        data=f"jd text {tag}".encode(),
    )

    llm.queue(
        fit_prompt.PROMPT_VERSION,
        FitCheck.model_validate({**VALID, "summary": f"fit-{tag}"}),
    )
    await matching.analyze(db, llm, org_id=org.id, job_id=job.id)

    llm.queue(
        letters_prompt.PROMPT_VERSION,
        LetterDraft(
            subject=f"subject-{tag}",
            salutation="Madame, Monsieur,",
            opening=f"opening-{tag}",
            body=[f"body-{tag}"],
            closing="Cordialement.",
        ),
    )
    letter = await letters.generate(db, llm, org_id=org.id, job_id=job.id)
    await letters.edit_block(
        db, org_id=org.id, letter_id=letter.id, block="opening", text=f"edited-{tag}"
    )  # a second version

    await applications.create_application(
        db,
        org_id=org.id,
        data=ApplicationIn(job_id=job.id, notes=f"notes-{tag}", status="applied"),
    )

    conversation = await coach.create_conversation(db, org_id=org.id, job_id=job.id)
    llm.queue_stream(coach_prompt.PROMPT_VERSION, [f"coach-answer-{tag}"])
    async for _ in coach.stream_reply(
        db,
        llm,
        org_id=org.id,
        conversation_id=conversation.id,
        content=f"coach-question-{tag}",
    ):
        pass

    ai_call_id = await usage.reserve_call(
        db, org_id=org.id, user_id=user.id, feature="seed", model="m",
        prompt_version="seed@1", quota=100,
    )  # fmt: skip
    await usage.finish_call(
        db, ai_call_id, input_tokens=5, output_tokens=7, latency_ms=3, status="ok"
    )
    db.add(TaskRun(org_id=org.id, kind="seed", status="done"))
    await db.commit()
    return OrgData(org, user, tag, [cv.storage_key, jd.storage_key], org.id, user.id)
