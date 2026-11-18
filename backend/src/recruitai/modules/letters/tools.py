"""The letter tool of the career pack (ADR 0039): drafts a cover letter for the job, like the Letters
page does (fit analysis, reused if there is one, then the letter)."""

from typing import cast

from recruitai.core.tools import Call, NoJob, Tool, register
from recruitai.modules.identity import service as identity
from recruitai.modules.letters import service as letters
from recruitai.modules.letters.schemas import CompanyType


async def _letter_draft(c: Call) -> dict[str, str]:
    if c.job_id is None or c.user_id is None:
        raise NoJob()
    employer = c.get("employer").strip().lower()
    language = await identity.user_language(c.db, c.user_id)
    await c.db.commit()  # nothing held open across the model calls
    letter = await letters.generate(
        c.db,
        c.llm,
        org_id=c.org_id,
        job_id=c.job_id,
        language=language,
        company_type=cast(
            CompanyType, employer if employer in ("startup", "phd") else "corporate"
        ),
    )
    return {"letter_id": str(letter.id), "subject": letter.content.get("subject") or ""}


register(
    Tool(
        "letter_draft",
        "career",
        (("start", False), ("employer", False)),
        ("letter_id", "subject"),
        effect="write",
        ai_uses=2,  # the fit analysis (none if one exists) and the letter
        needs_job=True,
        page="/letters",
        chat=True,
    ),
    _letter_draft,
)
