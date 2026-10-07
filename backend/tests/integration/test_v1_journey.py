"""The whole v1 individual journey (ARCHITECTURE.md §8.1) through /api/v1 (P2-33).

Real Postgres (committed), the real Firebase emulator, the real worker; only the three
external things are fake: the language model, the job board, and the PDF compiler (the real
Tectonic is exercised in the worker-image check). One test, because the point is that the
modules work *together*: profile → jobs → fit → letter (edit, check, PDF) → application →
coach → export (every module's data) → delete (all of it, and the identity)."""

import io
import zipfile
from uuid import uuid4

import firebase_admin
import httpx
import pytest
from firebase_admin import auth as firebase_auth
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts import coach as coach_prompt
from recruitai.ai.prompts import fit as fit_prompt
from recruitai.ai.prompts import letters as letters_prompt
from recruitai.core.storage import LocalStorage, ObjectNotFound
from recruitai.modules.letters import tasks as letters_tasks
from recruitai.modules.matching.schemas import FitCheck
from tests.fixtures.auth import mint_emulator_token
from tests.integration.test_coach_router import parse_sse
from tests.integration.test_letters_service import DRAFT
from tests.integration.test_matching_router import _add_job, _add_profile
from tests.unit.test_schemas import VALID

PDF = b"%PDF-1.4 the letter"


async def _purge(db_engine: AsyncEngine, uid: str) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM organizations WHERE id IN (SELECT m.org_id FROM memberships m"
                " JOIN users u ON u.id = m.user_id WHERE u.firebase_uid = :u)"
            ),
            {"u": uid},
        )
        await conn.execute(
            text("DELETE FROM users WHERE firebase_uid = :u"), {"u": uid}
        )
    try:
        firebase_auth.delete_user(uid, app=firebase_admin.get_app())
    except (firebase_auth.UserNotFoundError, ValueError):
        pass


async def test_the_whole_v1_journey_from_sign_in_to_account_deletion(
    real_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    task_app,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_compile(tex: str) -> bytes:
        return PDF

    monkeypatch.setattr(letters_tasks, "compile_tex", fake_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    tag = uuid4().hex[:8]
    uid, email = f"uid-journey-{tag}", f"journey-{tag}@example.com"
    who = {"Authorization": f"Bearer {mint_emulator_token(uid, email)}"}
    api = real_client

    try:
        # 1. Sign in: the first request provisions a personal org; no profile yet.
        me = (await api.get("/api/v1/me", headers=who)).json()
        assert me["user"]["email"] == email and me["onboarding"] == {
            "has_profile": False
        }
        org_id = me["active_org_id"]
        assert (await api.get("/api/v1/profile", headers=who)).status_code == 404

        # 2. Master profile: upload a CV once, extract it, see it, edit it.
        await _add_profile(api, fake_llm, who)
        assert (await api.get("/api/v1/me", headers=who)).json()["onboarding"][
            "has_profile"
        ] is True
        profile = (await api.get("/api/v1/profile", headers=who)).json()
        assert profile["data"]["personal_info"]["name"] == "Ada"
        patched = await api.patch(
            "/api/v1/profile", headers=who, json={"summary": "Backend engineer"}
        )
        assert patched.json()["data"]["summary"] == "Backend engineer"

        # 3. Job inbox: paste a job, search France Travail, save a result.
        job_id = await _add_job(api, fake_llm, who)
        search = (
            await api.get(
                "/api/v1/jobs/search?query=python&department=Paris", headers=who
            )
        ).json()
        assert search["results"][0]["id"] == "AB1"
        saved = await api.post(
            "/api/v1/jobs",
            headers=who,
            json={"source": "france_travail", "external_id": "AB1"},
        )
        assert saved.status_code == 201
        assert len((await api.get("/api/v1/jobs", headers=who)).json()) == 2

        # 4. Fit report for the pasted job (synchronous, stored).
        fake_llm.queue(fit_prompt.PROMPT_VERSION, FitCheck.model_validate(VALID))
        fit = await api.post(
            "/api/v1/fit-analyses",
            headers=who,
            json={"job_id": job_id, "company_type": "startup"},
        )
        assert fit.status_code == 201 and fit.json()["verdict"] == "go"

        # 5. Letter: generate, edit one block, check it, render the PDF, download it.
        fake_llm.queue(letters_prompt.PROMPT_VERSION, DRAFT)
        letter = (
            await api.post(
                "/api/v1/letters", headers=who, json={"job_id": job_id, "tone": "warm"}
            )
        ).json()
        lurl = f"/api/v1/letters/{letter['id']}"
        assert (
            letter["content"]["header"]["name"] == "Ada"
        )  # from the profile, not the model
        await api.patch(
            f"{lurl}/blocks/subject", headers=who, json={"text": "Candidature (v2)"}
        )
        check = (await api.get(f"{lurl}/check", headers=who)).json()
        assert check["quality"]["target_words"] == 250
        assert (await api.get(f"{lurl}/export?format=email", headers=who)).json()[
            "subject"
        ] == "Candidature (v2)"
        assert len((await api.get(f"{lurl}/versions", headers=who)).json()) == 2
        render = (await api.post(f"{lurl}/render", headers=who)).json()
        await task_app.run_worker_async(wait=False, install_signal_handlers=False)
        rendered = (await api.get(render["status_url"], headers=who)).json()
        assert rendered["status"] == "done" and rendered["download_url"]
        assert (await api.get(rendered["download_url"])).content == PDF
        assert (await api.get(lurl, headers=who)).json()["render_status"] == "done"

        # 6. Track the application and move it along.
        app_ = (
            await api.post(
                "/api/v1/applications",
                headers=who,
                json={"job_id": job_id, "source": "linkedin"},
            )
        ).json()
        for status in ("applied", "interview"):
            moved = await api.post(
                f"/api/v1/applications/{app_['id']}/status",
                headers=who,
                json={"status": status},
            )
            assert moved.status_code == 200
        illegal = await api.post(
            f"/api/v1/applications/{app_['id']}/status",
            headers=who,
            json={"status": "to_apply"},
        )
        assert illegal.status_code == 422
        timeline = (
            await api.get(f"/api/v1/applications/{app_['id']}/events", headers=who)
        ).json()
        assert [e["to_status"] for e in timeline] == [
            "to_apply",
            "applied",
            "interview",
        ]

        # 7. Coach: a streamed conversation about this job, kept in the history.
        conversation = (
            await api.post(
                "/api/v1/coach/conversations", headers=who, json={"job_id": job_id}
            )
        ).json()
        fake_llm.queue_stream(
            coach_prompt.PROMPT_VERSION, ["Mets en avant ", "ton stage."]
        )
        reply = await api.post(
            f"/api/v1/coach/conversations/{conversation['id']}/messages",
            headers=who,
            json={"content": "Conseils ?"},
        )
        assert [n for n, _ in parse_sse(reply.text)] == ["token", "token", "done"]
        history = (
            await api.get(
                f"/api/v1/coach/conversations/{conversation['id']}/messages",
                headers=who,
            )
        ).json()
        assert [m["role"] for m in history] == ["user", "assistant"]

        # 8. Export: everything the account holds, from every module, coach included.
        export = (await api.post("/api/v1/me/export", headers=who)).json()
        await task_app.run_worker_async(wait=False, install_signal_handlers=False)
        done = (await api.get(export["status_url"], headers=who)).json()
        assert done["status"] == "done"
        archive = zipfile.ZipFile(
            io.BytesIO((await api.get(done["download_url"])).content)
        )
        names = set(archive.namelist())
        assert {"profile.json", "jobs.json", "fit_analyses.json", "letters.json", "letter_versions.json",
                "applications.json", "application_events.json", "coach_messages.json",
                "documents.json", "manifest.json"} <= names  # fmt: skip
        text_all = "\n".join(
            archive.read(n).decode("utf-8", "ignore")
            for n in names
            if n.endswith(".json")
        )
        assert (
            "Conseils ?" in text_all and "Candidature (v2)" in text_all
        )  # coach + letter content
        assert any(
            n.startswith("files/letter_pdf/") for n in names
        )  # the rendered PDF travels too

        # 9. Delete the account: all rows, all files, the identity. A fresh sign-in is empty.
        files = [
            r[0]
            for r in (
                await _all(
                    db_engine,
                    "SELECT storage_key FROM documents WHERE org_id = :o",
                    org_id,
                )
            )
        ]
        assert files
        assert (await api.delete("/api/v1/me", headers=who)).status_code == 204
        for key in files:
            with pytest.raises(ObjectNotFound):
                await fake_storage.get(key)
        with pytest.raises(firebase_auth.UserNotFoundError):
            firebase_auth.get_user(uid, app=firebase_admin.get_app())
        assert (
            await _all(db_engine, "SELECT 1 FROM organizations WHERE id = :o", org_id)
        ) == []
        assert (
            await api.delete("/api/v1/me", headers=who)
        ).status_code == 401  # the old token is dead

        again = {
            "Authorization": f"Bearer {mint_emulator_token(uid + '-again', email)}"
        }
        fresh = (await api.get("/api/v1/me", headers=again)).json()
        assert fresh["active_org_id"] != org_id and fresh["onboarding"] == {
            "has_profile": False
        }
        assert (await api.get("/api/v1/jobs", headers=again)).json() == []
        assert (await api.get("/api/v1/applications", headers=again)).json() == []
    finally:
        await _purge(db_engine, uid)
        await _purge(db_engine, uid + "-again")


async def _all(db_engine: AsyncEngine, sql: str, org_id: str) -> list:
    async with db_engine.connect() as conn:
        return list((await conn.execute(text(sql), {"o": org_id})).all())
