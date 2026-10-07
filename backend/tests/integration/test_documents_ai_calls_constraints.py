"""P1-03: behaviour of the `documents` / `ai_calls` constraints (one test per rule)."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
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


async def _accepts(session: AsyncSession, make, **over) -> None:
    async with session.begin_nested():
        session.add(make(**over))


async def _rejects(
    session: AsyncSession, make, match: str | None = None, **over
) -> None:
    """The DB must refuse this row. `over` names the offending value in a failed assertion."""
    with pytest.raises((IntegrityError, DBAPIError), match=match) as _:
        async with session.begin_nested():
            session.add(make(**over))


# ------------------------------------------------------------------ documents


async def test_document_round_trip_ids_defaults_and_bigint_size(
    db_session: AsyncSession,
):
    org, user = await _org(db_session), await _user(db_session)
    org_id = org.id
    doc = _doc(org, uploaded_by=user.id, size=10 * 1024**3)  # > 32 bits
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
        10 * 1024**3,
        SHA,
    )
    assert abs(datetime.now(UTC) - loaded.created_at) < timedelta(minutes=1)


async def test_document_kind_and_size_and_sha256_rules(db_session: AsyncSession):
    org = await _org(db_session)
    for kind in ("cv", "jd", "letter_pdf", "attachment"):
        await _accepts(db_session, lambda **o: _doc(org, **o), kind=kind)
    for bad in ("", "CV", "docx", "resume"):
        await _rejects(
            db_session, lambda **o: _doc(org, **o), "ck_documents_kind", kind=bad
        )
    await _rejects(db_session, lambda **o: _doc(org, **o), "ck_documents_size", size=-1)
    for bad in ("", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65):
        await _rejects(db_session, lambda **o: _doc(org, **o), sha256=bad)


async def test_document_storage_key_is_unique_and_org_and_required_fields_enforced(
    db_session: AsyncSession,
):
    org = await _org(db_session)
    await _accepts(db_session, lambda **o: _doc(org, **o), storage_key="orgs/x/cv/1")
    await _rejects(
        db_session,
        lambda **o: _doc(org, **o),
        "uq_documents_storage_key",
        storage_key="orgs/x/cv/1",
    )
    ghost = Organization(
        id=uuid.uuid4(), name="ghost", kind="personal"
    )  # never persisted
    await _rejects(db_session, lambda **o: _doc(ghost, **o), "fk_documents_org_id")
    for field in ("kind", "storage_key", "mime", "size", "sha256"):
        await _rejects(db_session, lambda **o: _doc(org, **o), **{field: None})


async def test_document_uploader_is_optional_and_deleting_it_keeps_the_document(
    db_session: AsyncSession,
):
    org, user = await _org(db_session), await _user(db_session)
    system_doc = _doc(org, kind="letter_pdf", uploaded_by=None)  # e.g. a rendered PDF
    owned = _doc(org, uploaded_by=user.id)
    db_session.add_all([system_doc, owned])
    await db_session.flush()
    owned_id, user_id = owned.id, user.id

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    db_session.expire_all()

    kept = (
        await db_session.execute(select(Document).where(Document.id == owned_id))
    ).scalar_one()
    assert kept.uploaded_by is None


async def test_deleting_an_org_deletes_only_its_documents_and_queries_filter_by_org(
    db_session: AsyncSession,
):
    a, b = await _org(db_session, "A"), await _org(db_session, "B")
    db_session.add_all([_doc(a), _doc(a), _doc(b)])
    await db_session.flush()
    only_a = (
        (await db_session.execute(select(Document).where(Document.org_id == a.id)))
        .scalars()
        .all()
    )
    assert len(only_a) == 2 and {d.org_id for d in only_a} == {a.id}

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": a.id}
    )

    assert (await db_session.execute(select(Document.org_id))).scalars().all() == [b.id]


# ------------------------------------------------------------------ ai_calls


async def test_ai_call_round_trip_and_db_defaults(db_session: AsyncSession):
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
    assert (loaded.input_tokens, loaded.output_tokens) == (0, 0)
    assert (loaded.feature, loaded.model, loaded.prompt_version) == (
        "cv_extraction",
        "gemini-2.5-flash",
        "v1",
    )
    assert loaded.created_at.tzinfo is not None


async def test_ai_call_status_counts_latency_and_required_fields(
    db_session: AsyncSession,
):
    org = await _org(db_session)
    for ok in ("ok", "error"):
        await _accepts(db_session, lambda **o: _call(org, **o), status=ok)
    for bad in ("", "OK", "failed", "blocked"):
        await _rejects(
            db_session, lambda **o: _call(org, **o), "ck_ai_calls_status", status=bad
        )
    for field in ("input_tokens", "output_tokens"):
        await _rejects(
            db_session, lambda **o: _call(org, **o), "ck_ai_calls_tokens", **{field: -1}
        )
    await _rejects(
        db_session, lambda **o: _call(org, **o), "ck_ai_calls_latency", latency_ms=-5
    )
    for field in ("feature", "model", "prompt_version", "latency_ms", "status"):
        await _rejects(db_session, lambda **o: _call(org, **o), **{field: None})
    ghost = Organization(id=uuid.uuid4(), name="ghost", kind="personal")
    await _rejects(db_session, lambda **o: _call(ghost, **o), "fk_ai_calls_org_id")


async def test_ai_calls_survive_user_deletion_anonymously_and_die_with_their_org(
    db_session: AsyncSession,
):
    a, b, user = (
        await _org(db_session, "A"),
        await _org(db_session, "B"),
        await _user(db_session),
    )
    call = _call(a, user_id=user.id)
    db_session.add_all([call, _call(b)])
    await db_session.flush()
    call_id, user_id, a_id, b_id = call.id, user.id, a.id, b.id

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    db_session.expire_all()
    kept = (
        await db_session.execute(select(AiCall).where(AiCall.id == call_id))
    ).scalar_one()
    assert kept.user_id is None  # metadata kept, person gone

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": a_id}
    )
    assert (await db_session.execute(select(AiCall.org_id))).scalars().all() == [b_id]
