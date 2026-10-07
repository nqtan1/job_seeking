"""All SQL for the letters module. Every query filters by org_id."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.letters.models import Letter, LetterVersion
from recruitai.modules.letters.schemas import SCHEMA_VERSION


async def get(
    session: AsyncSession, *, org_id: UUID, letter_id: UUID, for_update: bool = False
) -> Letter | None:
    """``for_update`` serializes edits of one letter, so version numbers never collide and
    two block edits can't drop each other."""
    stmt = select(Letter).where(Letter.org_id == org_id, Letter.id == letter_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_org(
    session: AsyncSession,
    *,
    org_id: UUID,
    job_id: UUID | None,
    limit: int,
    offset: int,
) -> list[Letter]:
    stmt = select(Letter).where(Letter.org_id == org_id)
    if job_id is not None:
        stmt = stmt.where(Letter.job_id == job_id)
    rows = await session.execute(
        stmt.order_by(Letter.created_at.desc(), Letter.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def create(
    session: AsyncSession,
    *,
    org_id: UUID,
    job_id: UUID,
    template: str,
    language: str,
    tone: str,
    length: str,
    company_type: str,
    content: dict[str, Any],
) -> Letter:
    """The letter and its first version, in the caller's transaction."""
    letter = Letter(
        org_id=org_id,
        job_id=job_id,
        template=template,
        language=language,
        tone=tone,
        length=length,
        company_type=company_type,
        content=content,
        schema_version=SCHEMA_VERSION,
    )
    session.add(letter)
    await session.flush()
    session.add(LetterVersion(letter_id=letter.id, n=1, org_id=org_id, content=content))
    await session.flush()
    await session.refresh(letter)  # server-side created_at / updated_at
    return letter


async def save_content(
    session: AsyncSession, letter: Letter, content: dict[str, Any]
) -> Letter:
    """Set the letter's content and append it as the next version. Call with the row locked
    (``get(..., for_update=True)``)."""
    last = await session.scalar(
        select(func.max(LetterVersion.n)).where(LetterVersion.letter_id == letter.id)
    )
    letter.content = content
    # The PDF (if any) was made from the previous content: the letter is no longer rendered.
    letter.render_status = "none"
    session.add(
        LetterVersion(
            letter_id=letter.id,
            n=(last or 0) + 1,
            org_id=letter.org_id,
            content=content,
        )
    )
    await session.flush()
    await session.refresh(letter)
    return letter


async def list_versions(
    session: AsyncSession, *, org_id: UUID, letter_id: UUID
) -> list[LetterVersion]:
    rows = await session.execute(
        select(LetterVersion)
        .where(LetterVersion.org_id == org_id, LetterVersion.letter_id == letter_id)
        .order_by(LetterVersion.n.desc())
    )
    return list(rows.scalars())


async def get_version(
    session: AsyncSession, *, org_id: UUID, letter_id: UUID, n: int
) -> LetterVersion | None:
    return (
        await session.execute(
            select(LetterVersion).where(
                LetterVersion.org_id == org_id,
                LetterVersion.letter_id == letter_id,
                LetterVersion.n == n,
            )
        )
    ).scalar_one_or_none()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[Letter]:
    rows = await session.execute(
        select(Letter).where(Letter.org_id == org_id).order_by(Letter.created_at)
    )
    return list(rows.scalars())


async def all_versions_for_org(
    session: AsyncSession, *, org_id: UUID
) -> list[LetterVersion]:
    rows = await session.execute(
        select(LetterVersion)
        .where(LetterVersion.org_id == org_id)
        .order_by(LetterVersion.letter_id, LetterVersion.n)
    )
    return list(rows.scalars())
