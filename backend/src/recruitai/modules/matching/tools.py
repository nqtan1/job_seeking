"""The fit check tool of the career pack (ADR 0039)."""

from typing import cast

from recruitai.core.tools import Call, NoJob, Tool, register
from recruitai.modules.identity import service as identity
from recruitai.modules.matching import service as matching
from recruitai.modules.matching.models import FitAnalysis
from recruitai.modules.matching.schemas import CompanyType

FIT_OUTPUTS = ("score", "verdict", "strengths", "gaps", "missing", "reasons")


async def _fit_check(c: Call) -> dict[str, str]:
    """The app's own fit analysis (tested prompts, one persona per employer type) of the job
    against the account's profile. An existing analysis of the job is reused."""
    if c.job_id is None or c.user_id is None:
        raise NoJob()
    employer = c.get("employer").strip().lower()
    company_type = cast(
        CompanyType, employer if employer in ("startup", "phd") else "corporate"
    )
    language = await identity.user_language(c.db, c.user_id)
    await c.db.commit()  # nothing held open across the model call
    row = await matching.latest_or_analyze(
        c.db,
        c.llm,
        org_id=c.org_id,
        job_id=c.job_id,
        company_type=company_type,
        language=language,
    )

    return _fields(row)


def _fields(row: FitAnalysis) -> dict[str, str]:
    def bullets(key: str) -> str:
        return "\n".join(f"- {x}" for x in row.data.get(key) or [])

    return {
        "score": str(row.score),
        "verdict": row.verdict,
        "strengths": bullets("strengths"),
        "gaps": bullets("gaps"),
        "missing": bullets("key_missing_requirements"),
        "reasons": bullets("reasons"),
    }


async def _fit_read(c: Call) -> dict[str, str]:
    """The latest stored fit analysis of the job, never a new one (no model call: safe in chat)."""
    if c.job_id is None:
        raise NoJob()
    rows = await matching.list_analyses(c.db, org_id=c.org_id, job_id=c.job_id, limit=1)
    if not rows:
        return dict.fromkeys(FIT_OUTPUTS, "") | {"verdict": "none yet"}
    return _fields(rows[0])


# the fit analysis of the run's job (the app's tested fit prompts); "start" hangs it off Start
register(
    Tool(
        "fit_check",
        "career",
        (("start", False), ("employer", False)),
        FIT_OUTPUTS,
        ai_uses=1,
        needs_job=True,
    ),
    _fit_check,
)
# reads the stored fit analysis only (the chat's fit tool: it never starts a model call)
register(
    Tool(
        "fit_read",
        "career",
        (("start", False),),
        FIT_OUTPUTS,
        needs_job=True,
        chat=True,
    ),
    _fit_read,
)
