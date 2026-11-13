"""/api/v1/cv-reviews through real HTTP and the real worker (committed data); LLM faked."""

import httpx

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.cv_review import PROMPT_VERSION
from recruitai.config import get_settings
from recruitai.core.storage import LocalStorage
from recruitai.modules.cvreview.schemas import (
    BlockComment,
    LlmDimension,
    LlmReview,
    LlmSummary,
    Quote,
    Strength,
)
from tests.unit.test_cvreview_pdfview import _pdf

BASE = "/api/v1/cv-reviews"
CV = b"""Ada Lovelace
ada@example.test | github.com/ada

SUMMARY
Passionate engineer.

EXPERIENCE
- Built a billing API in Python serving 12 clients
- Responsible for deployments
- Cut p95 latency by 40% with Redis caching

SKILLS
Python, Redis
"""


def _c(block_id, rating, *quotes, **kw):
    return BlockComment(
        block_id=block_id, criterion="impact.metric", rating=rating, why="why", improve=None,
        citations=[Quote(block_id=block_id, quote=q) for q in quotes], **{"rewrite": None, **kw},
    )  # fmt: skip


def _review(*comments):
    dim = LlmDimension(reason="because", block_ids=["b8", "b99"], score=60)
    return LlmReview(
        comments=list(comments),
        summary=LlmSummary(
            strengths=[Strength(text="Redis", block_id="b8"), Strength(text="x", block_id="b99")],
            top_fixes=["b7", "b99"],
        ),
        scope=dim, stack=dim, projects=dim, progression=dim,
    )  # fmt: skip


async def _run(task_app, client, headers, body) -> dict:
    accepted = await client.post(BASE, headers=headers, json=body)
    assert accepted.status_code == 202, accepted.text
    status_url = accepted.json()["status_url"]
    assert (await client.get(status_url, headers=headers)).json()["status"] == "queued"
    await task_app.run_worker_async(wait=False, install_signal_handlers=False)
    done = (await client.get(status_url, headers=headers)).json()
    assert (done["status"], done["error_code"]) == ("done", None)
    return (await client.get(f"{BASE}/{done['result_ref']}", headers=headers)).json()


async def test_review_flow_grounding_edit_tenancy_flag_and_recheck(
    real_client: httpx.AsyncClient,
    real_app,
    task_app,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    users,
    monkeypatch,
):
    ada, bob = users["ada"], users["bob"]
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    monkeypatch.setattr(
        "recruitai.ai.dependencies.build_llm_gateway", lambda *a, **k: fake_llm
    )

    async def upload(who, data: bytes, name: str) -> str:
        r = await real_client.post(
            "/api/v1/documents", headers=who, data={"kind": "cv"},
            files={"file": (name, data, "text/plain")},
        )  # fmt: skip
        return r.json()["document_id"]

    doc = await upload(ada, CV, "cv.txt")
    body = {"document_id": doc, "track": "backend", "level": "junior"}

    # (a) grounded review; b10 (skills) is skipped by the model and gets a rule comment
    fake_llm.queue(
        PROMPT_VERSION,
        _review(
            _c("b4", "poor", "Passionate engineer."),
            _c("b6", "moderate", "made-up words", rewrite="Built a billing API for [N] clients"),
            _c("b7", "poor", rewrite="Owned deployments, 99% faster"),
            _c("b8", "good", "p95  latency by 40%"),
            _c("b3", "poor"),  # a heading
            _c("b99", "poor"),  # unknown id
        ),
    )  # fmt: skip
    first = await _run(task_app, real_client, ada, body)
    cs = {c["block_id"]: c for c in first["data"]["comments"]}
    assert list(cs) == ["b4", "b6", "b7", "b8", "b10"]
    quotes = lambda k: [q["quote"] for q in cs[k]["citations"]]
    assert (
        quotes("b4") == ["Passionate engineer."]
        and cs["b4"]["criterion"] == "impact.metric"
    )
    assert quotes("b6") == [] and "[N]" in cs["b6"]["rewrite"]
    assert cs["b7"]["rewrite"] is None  # 99 is not in the original block
    assert quotes("b8") == ["p95 latency by 40%"]  # relocated to the block's exact text
    assert cs["b10"]["rating"] == "good" and "automatic" in cs["b10"]["why"]
    assert (
        quotes("b10") == []
        and cs["b10"]["source"] == "rule"
        and cs["b4"]["source"] == "ai"
    )  # no tag: nothing to cite
    assert first["data"]["truncated"] is False
    assert first["data"]["summary"]["top_fixes"] == ["b7"]
    dims = first["data"]["dimensions"]
    assert dims["scope"]["block_ids"] == ["b8"] and dims["scope"]["reason"] == "because"
    assert dims["impact"]["reason"] is None and "b7" in dims["impact"]["block_ids"]
    assert first["data"]["summary"]["strengths"] == [
        {"text": "Redis", "block_id": "b8"},
        {"text": "x", "block_id": None},
    ]
    assert first["data"]["grounding_rate"] == 2 / 3 and 0 <= first["score"] <= 100
    assert set(first["data"]["dimensions"]) >= {"impact", "scope", "stack", "structure"}
    assert (first["model"], first["prompt_version"], first["parent_id"]) == (
        "fake-smart",
        PROMPT_VERSION,
        None,
    )

    # (b) another org sees nothing and cannot use this org's document or review
    one = f"{BASE}/{first['id']}"
    assert (await real_client.get(one, headers=bob)).status_code == 404
    assert (await real_client.delete(one, headers=bob)).status_code == 404
    assert (await real_client.post(BASE, headers=bob, json=body)).status_code == 404
    stolen = {"parent_review_id": first["id"], "blocks": first["data"]["blocks"][:2],
              "track": "backend", "level": "junior"}  # fmt: skip
    assert (await real_client.post(BASE, headers=bob, json=stolen)).status_code == 404
    assert (await real_client.get(BASE, headers=bob)).json() == []

    # (c) edited blocks re-evaluate into a new row linked to the parent
    blocks = first["data"]["blocks"]
    blocks[6]["text"] = "Owned deployments with GitHub Actions, shipping 3 times a week"
    fake_llm.queue(PROMPT_VERSION, _review(_c("b7", "good")))
    second = await _run(
        task_app, real_client, ada,
        {"parent_review_id": first["id"], "blocks": blocks, "track": "backend", "level": "junior"},
    )  # fmt: skip
    assert second["parent_id"] == first["id"] and second["id"] != first["id"]
    assert second["data"]["blocks"][6]["text"].startswith("Owned deployments")
    listed = (await real_client.get(BASE, headers=ada)).json()
    assert [r["id"] for r in listed] == [second["id"], first["id"]]

    # a scan (no text layer) is refused before anything is queued
    scan = await upload(ada, b"%PDF-1.4\n%scan", "scan.pdf")
    bad = await real_client.post(BASE, headers=ada, json={**body, "document_id": scan})
    assert (bad.status_code, bad.json()["code"]) == (422, "cv_unparseable")

    # (e) recheck is rules only: no model call, no quota
    calls = len(fake_llm.calls)
    rc = await real_client.post(
        f"{BASE}/recheck", headers=ada,
        json={"blocks": blocks, "track": "backend", "level": "junior"},
    )  # fmt: skip
    out = rc.json()
    assert rc.status_code == 200 and len(fake_llm.calls) == calls
    sig = out["signals"]
    assert "no_metric" not in sig["b6"] and "weak_verb" not in sig["b7"]
    assert 0 <= out["score"] <= 100 and "impact" in out["dimensions"]

    # (e) PDF uploads can be shown in place: layout + page image, org-scoped; text uploads cannot
    layout_url = f"{BASE}/{first['id']}/layout"
    no_pdf = await real_client.get(layout_url, headers=ada)
    assert (no_pdf.status_code, no_pdf.json()["code"]) == (404, "cv_no_pdf")
    pdf_doc = (
        await real_client.post(
            "/api/v1/documents", headers=ada, data={"kind": "cv"},
            files={"file": ("cv.pdf", _pdf(["Built a billing API in Python serving 12 clients"]), "application/pdf")},
        )
    ).json()["document_id"]  # fmt: skip
    fake_llm.queue(PROMPT_VERSION, _review(_c("b1", "good")))
    shown = await _run(task_app, real_client, ada, {**body, "document_id": pdf_doc})
    lay = await real_client.get(f"{BASE}/{shown['id']}/layout", headers=ada)
    assert lay.status_code == 200 and lay.json()["boxes"]  # the printed line was found
    page = await real_client.get(f"{BASE}/{shown['id']}/pages/1", headers=ada)
    assert page.content[:4] == b"\x89PNG" and page.headers["cache-control"].startswith(
        "private"
    )
    assert (
        await real_client.get(f"{BASE}/{shown['id']}/pages/2", headers=ada)
    ).status_code == 404
    assert (
        await real_client.get(f"{BASE}/{shown['id']}/layout", headers=bob)
    ).status_code == 404

    # (d) the flag turns every route off (create, read, delete, recheck)
    real_app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"cv_review_enabled": False}
    )
    for call in (
        real_client.post(BASE, headers=ada, json=body),
        real_client.get(f"{BASE}/{second['id']}", headers=ada),
        real_client.delete(f"{BASE}/{second['id']}", headers=ada),
    ):
        off = await call
        assert (off.status_code, off.json()["code"]) == (503, "cv_review_disabled")
    me = await real_client.get("/api/v1/me", headers=ada)  # the sidebar hides the page
    assert me.json()["cv_review_enabled"] is False
    real_app.dependency_overrides.pop(get_settings)
    assert (
        await real_client.delete(f"{BASE}/{second['id']}", headers=ada)
    ).status_code == 204
    assert (
        await real_client.get(f"{BASE}/{second['id']}", headers=ada)
    ).status_code == 404
