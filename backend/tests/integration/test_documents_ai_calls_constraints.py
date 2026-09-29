"""P1-03: behaviour of the `documents` / `ai_calls` constraints, plus ORM insert/select smoke."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.usage import AiCall
from recruitai.modules.documents.models import Document
from recruitai.modules.identity.models import Organization, User

SHA = hashlib.sha256(b"cv").hexdigest()


async def _org(session: AsyncSession, name: str = "Ada") -> Organization:
    org = Organization(name=name, kind="personal")
    session.add(org)
    await session.flush()
    return org


async def _user(session: AsyncSession, uid: str = "fb-doc") -> User:
    user = User(firebase_uid=uid, email=f"{uid}@example.test")
    session.add(user)
    await session.flush()
    return user


def _doc(org: Organization, **over) -> Document:
    values = {
        "org_id": org.id,
        "kind": "cv",
        "storage_key": f"orgs/{org.id}/cv/{uuid.uuid4()}",
        "mime": "application/pdf",
        "size": 1234,
        "sha256": SHA,
    }
    return Document(**{**values, **over})


def _call(org: Organization, **over) -> AiCall:
    values = {
        "org_id": org.id,
        "feature": "cv_extraction",
        "model": "gemini-2.5-flash",
        "prompt_version": "v1",
        "latency_ms": 420,
        "status": "ok",
    }
    return AiCall(**{**values, **over})


async def _fails(session: AsyncSession, obj, match: str | None = None) -> None:
    with pytest.raises(IntegrityError, match=match):
        async with session.begin_nested():
            session.add(obj)


# ------------------------------------------------------------------ documents


async def test_document_round_trip(db_session: AsyncSession):
    org, user = await _org(db_session), await _user(db_session)
    org_id = org.id
    doc = _doc(org, uploaded_by=user.id)
    db_session.add(doc)
    await db_session.flush()
    doc_id = doc.id
    db_session.expire_all()

    loaded = (
        await db_session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one()

    assert loaded.id.version == 7
    assert (loaded.org_id, loaded.kind, loaded.size, loaded.sha256) == (
        org_id,
        "cv",
        1234,
        SHA,
    )
    assert loaded.created_at.tzinfo is not None
    assert abs(datetime.now(UTC) - loaded.created_at) < timedelta(minutes=1)


async def test_document_size_can_exceed_32_bits(db_session: AsyncSession):
    org = await _org(db_session)
    doc = _doc(org, size=10 * 1024**3)
    db_session.add(doc)

    await db_session.flush()

    assert doc.size == 10 * 1024**3


@pytest.mark.parametrize("kind", ["", "CV", "docx", "resume"])
async def test_document_rejects_unknown_kind(db_session: AsyncSession, kind: str):
    await _fails(
        db_session, _doc(await _org(db_session), kind=kind), "ck_documents_kind"
    )


@pytest.mark.parametrize("kind", ["cv", "jd", "letter_pdf", "attachment"])
async def test_document_accepts_every_documented_kind(
    db_session: AsyncSession, kind: str
):
    db_session.add(_doc(await _org(db_session), kind=kind))

    await db_session.flush()


async def test_document_rejects_negative_size(db_session: AsyncSession):
    await _fails(db_session, _doc(await _org(db_session), size=-1), "ck_documents_size")


@pytest.mark.parametrize("sha", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
async def test_document_rejects_malformed_sha256(db_session: AsyncSession, sha: str):
    org = await _org(db_session)

    with pytest.raises(Exception):  # noqa: B017  (too long -> DataError, else IntegrityError)
        async with db_session.begin_nested():
            db_session.add(_doc(org, sha256=sha))


async def test_document_storage_key_is_unique(db_session: AsyncSession):
    org = await _org(db_session)
    db_session.add(_doc(org, storage_key="orgs/x/cv/1"))
    await db_session.flush()

    await _fails(
        db_session, _doc(org, storage_key="orgs/x/cv/1"), "uq_documents_storage_key"
    )


async def test_document_requires_an_existing_org(db_session: AsyncSession):
    bogus = Organization(
        id=uuid.uuid4(), name="ghost", kind="personal"
    )  # never persisted

    await _fails(db_session, _doc(bogus), "fk_documents_org_id")


@pytest.mark.parametrize("field", ["kind", "storage_key", "mime", "size", "sha256"])
async def test_document_required_fields(db_session: AsyncSession, field: str):
    await _fails(db_session, _doc(await _org(db_session), **{field: None}))


async def test_system_documents_may_have_no_uploader(db_session: AsyncSession):
    doc = _doc(await _org(db_session), kind="letter_pdf", uploaded_by=None)
    db_session.add(doc)

    await db_session.flush()

    assert doc.uploaded_by is None


async def test_deleting_the_uploader_keeps_the_document(db_session: AsyncSession):
    org, user = await _org(db_session), await _user(db_session)
    user_id = user.id
    doc = _doc(org, uploaded_by=user_id)
    db_session.add(doc)
    await db_session.flush()
    doc_id = doc.id

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    db_session.expire_all()

    kept = (
        await db_session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one()
    assert kept.uploaded_by is None


async def test_deleting_an_org_deletes_its_documents_only(db_session: AsyncSession):
    a, b = await _org(db_session, "A"), await _org(db_session, "B")
    db_session.add_all([_doc(a), _doc(b)])
    await db_session.flush()

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": a.id}
    )

    left = (await db_session.execute(select(Document.org_id))).scalars().all()
    assert left == [b.id]


async def test_documents_filtered_by_org_only_return_that_orgs_rows(
    db_session: AsyncSession,
):
    a, b = await _org(db_session, "A"), await _org(db_session, "B")
    db_session.add_all([_doc(a), _doc(a), _doc(b)])
    await db_session.flush()

    rows = (
        (await db_session.execute(select(Document).where(Document.org_id == a.id)))
        .scalars()
        .all()
    )

    assert len(rows) == 2 and {r.org_id for r in rows} == {a.id}


# ------------------------------------------------------------------ ai_calls


async def test_ai_call_round_trip_with_defaults(db_session: AsyncSession):
    org, user = await _org(db_session), await _user(db_session)
    call = _call(org, user_id=user.id)
    db_session.add(call)
    await db_session.flush()
    call_id = call.id
    db_session.expire_all()

    loaded = (
        await db_session.execute(select(AiCall).where(AiCall.id == call_id))
    ).scalar_one()

    assert loaded.id.version == 7
    assert (loaded.input_tokens, loaded.output_tokens) == (0, 0)  # DB defaults
    assert (loaded.feature, loaded.model, loaded.prompt_version) == (
        "cv_extraction",
        "gemini-2.5-flash",
        "v1",
    )
    assert loaded.created_at.tzinfo is not None


@pytest.mark.parametrize("status", ["ok", "error"])
async def test_ai_call_accepts_documented_statuses(
    db_session: AsyncSession, status: str
):
    db_session.add(_call(await _org(db_session), status=status))

    await db_session.flush()


@pytest.mark.parametrize("status", ["", "OK", "failed", "blocked"])
async def test_ai_call_rejects_unknown_status(db_session: AsyncSession, status: str):
    await _fails(
        db_session, _call(await _org(db_session), status=status), "ck_ai_calls_status"
    )


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
async def test_ai_call_rejects_negative_tokens(db_session: AsyncSession, field: str):
    await _fails(
        db_session, _call(await _org(db_session), **{field: -1}), "ck_ai_calls_tokens"
    )


async def test_ai_call_rejects_negative_latency(db_session: AsyncSession):
    await _fails(
        db_session, _call(await _org(db_session), latency_ms=-5), "ck_ai_calls_latency"
    )


@pytest.mark.parametrize(
    "field", ["feature", "model", "prompt_version", "latency_ms", "status"]
)
async def test_ai_call_required_fields(db_session: AsyncSession, field: str):
    await _fails(db_session, _call(await _org(db_session), **{field: None}))


async def test_ai_call_requires_an_existing_org(db_session: AsyncSession):
    bogus = Organization(id=uuid.uuid4(), name="ghost", kind="personal")

    await _fails(db_session, _call(bogus), "fk_ai_calls_org_id")


async def test_deleting_a_user_keeps_their_ai_calls_as_anonymous_metadata(
    db_session: AsyncSession,
):
    org, user = await _org(db_session), await _user(db_session)
    user_id = user.id
    call = _call(org, user_id=user_id)
    db_session.add(call)
    await db_session.flush()
    call_id = call.id

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    db_session.expire_all()

    kept = (
        await db_session.execute(select(AiCall).where(AiCall.id == call_id))
    ).scalar_one()
    assert kept.user_id is None


async def test_deleting_an_org_deletes_its_ai_calls_only(db_session: AsyncSession):
    a, b = await _org(db_session, "A"), await _org(db_session, "B")
    db_session.add_all([_call(a), _call(b)])
    await db_session.flush()

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": a.id}
    )

    assert (await db_session.execute(select(AiCall.org_id))).scalars().all() == [b.id]
