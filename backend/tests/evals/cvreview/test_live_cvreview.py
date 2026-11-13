"""CV review eval: golden fixtures + pure scoring helpers. Live run is opt-in (RUN_LIVE_LLM=1, never CI)."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

from recruitai.modules.cvreview.checks import CRITERIA

HERE = Path(__file__).parent
GOLDEN = json.loads((HERE / "golden.json").read_text())
_ws = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _ws.sub(" ", s).strip().lower()


def _texts(blocks: list[dict]) -> dict[str, str]:
    return {b["id"]: _norm(b["text"]) for b in blocks}


def citation_validity(comments: list[dict], blocks: list[dict]) -> float:
    """Share of citations whose quote is an exact substring of its block (1.0 when there are none)."""
    text = _texts(blocks)
    cites = [q for c in comments for q in c.get("citations") or []]
    ok = sum(
        bool(q["quote"]) and _norm(q["quote"]) in text.get(q["block_id"], "")
        for q in cites
    )
    return ok / len(cites) if cites else 1.0


def unsupported_rate(comments: list[dict]) -> float:
    """Share of poor/moderate comments with no citation (target 0)."""
    bad = [c for c in comments if c.get("rating") != "good"]
    return sum(not c.get("citations") for c in bad) / len(bad) if bad else 0.0


def criterion_valid_rate(comments: list[dict], criteria: set[str]) -> float:
    """Share of comments whose criterion is a rubric id."""
    return (
        sum(c.get("criterion") in criteria for c in comments) / len(comments)
        if comments
        else 1.0
    )


def _hit(quote: str, c: dict, text: dict[str, str]) -> bool:
    """Comment c is about `quote`: one of its citations overlaps it, or the quote sits in c's block."""
    q = _norm(quote)
    for cit in c.get("citations") or []:
        ev = _norm(cit["quote"])
        if ev and (ev in q or q in ev):
            return True
    return q in text.get(c["block_id"], "")


def invented_numbers(rewrites: list[str], cv_text: str) -> list[str]:
    """Digit tokens in rewrites that never occur in the CV (placeholders like [X%] carry none)."""
    known = set(re.findall(r"\d+(?:[.,]\d+)?", cv_text))
    return sorted(
        {n for r in rewrites for n in re.findall(r"\d+(?:[.,]\d+)?", r)} - known
    )


def band_ok(score: int, band: list[int] | tuple[int, int]) -> bool:
    return band[0] <= score <= band[1]


def recall_of_flags(comments: list[dict], golden: dict, blocks: list[dict]) -> float:
    """Share of must_flag quotes hit by a poor/moderate comment."""
    text = _texts(blocks)
    bad = [c for c in comments if c.get("rating") in ("poor", "moderate")]
    flags = golden["must_flag"]
    return sum(any(_hit(f["quote"], c, text) for c in bad) for f in flags) / len(flags)


def criterion_accuracy(comments: list[dict], golden: dict, blocks: list[dict]) -> float:
    """Among must_flag quotes hit by a poor/moderate comment, share where one such comment
    picked an acceptable `expected_criteria` id (0.0 if none was hit)."""
    text = _texts(blocks)
    bad = [c for c in comments if c.get("rating") in ("poor", "moderate")]
    hits = [
        [c["criterion"] for c in bad if _hit(f["quote"], c, text)]
        for f in golden["must_flag"]
    ]
    pairs = [
        (h, f["expected_criteria"]) for h, f in zip(hits, golden["must_flag"]) if h
    ]
    return sum(bool(set(h) & set(e)) for h, e in pairs) / len(pairs) if pairs else 0.0


def explanation_problems(out: dict) -> list[str]:
    """Strengths must point to existing blocks; model-scored dimensions need a reason and valid block_ids."""
    ids = {b["id"] for b in out["blocks"]}
    bad = [f"strength {s['text'][:30]!r}: {s['block_id']}" for s in out["summary"]["strengths"]
           if s["block_id"] not in ids]  # fmt: skip
    for n in ("scope", "stack", "projects", "progression"):
        d = out["dimensions"][n]
        if (
            not (d.get("reason") or "").strip()
            or not set(d.get("block_ids") or []) <= ids
        ):
            bad.append(f"dimension {n}: reason/block_ids")
    return bad


def test_fixtures_and_helpers_offline():
    for g in GOLDEN.values():
        cv = (HERE / g["file"]).read_text()
        assert len([ln for ln in cv.splitlines() if ln.strip()]) >= 25
        assert len(g["must_flag"]) >= 4
        assert all(i["quote"] in cv for k in ("must_flag", "must_praise") for i in g[k])
        assert not [n for n in g["must_not_invent"] if n in cv]

    g = GOLDEN["junior_backend"]
    assert all(f["expected_criteria"] and set(f["expected_criteria"]) <= set(CRITERIA)
               for x in GOLDEN.values() for f in x["must_flag"])  # fmt: skip
    blocks = [
        {"id": "b1", "text": "Worked on authentication using JWT tokens"},
        {"id": "b2", "text": "Wrote 12 unit tests with pytest"},
    ]
    comments = [
        {"block_id": "b1", "rating": "poor", "criterion": "impact.outcome",
         "citations": [{"block_id": "b1", "quote": "Worked  on authentication"}]},
        {"block_id": "b2", "rating": "good", "criterion": "bogus",
         "citations": [{"block_id": "b2", "quote": "invented words"}]},
        {"block_id": "b2", "rating": "moderate", "criterion": "stack.named", "citations": []},
    ]  # fmt: skip
    assert citation_validity(comments, blocks) == 0.5
    assert unsupported_rate(comments) == 0.5
    assert criterion_valid_rate(comments, set(CRITERIA)) == pytest.approx(2 / 3)
    assert recall_of_flags(comments, g, blocks) == pytest.approx(1 / 5)
    assert criterion_accuracy(comments, g, blocks) == 1.0
    comments[0]["criterion"] = "structure.format"
    assert criterion_accuracy(comments, g, blocks) == 0.0
    out = {
        "blocks": blocks,
        "summary": {"strengths": [{"text": "x", "block_id": "b9"}]},
        "dimensions": {n: {"reason": "r", "block_ids": ["b1"]} for n in
                       ("scope", "stack", "projects", "progression")},
    }  # fmt: skip
    out["dimensions"]["stack"]["reason"] = " "
    assert len(explanation_problems(out)) == 2
    cv = (HERE / g["file"]).read_text()
    assert invented_numbers(
        ["Cut load by [X%] across 12 tests", "Served 9999 users"], cv
    ) == ["9999"]
    assert band_ok(50, g["band"]) and not band_ok(90, g["band"])


async def _run_service(db, cv_text: str, track: str, level: str) -> dict:
    """The real `evaluate` on a live Gemini gateway; the review as the API returns it."""
    from recruitai.ai import gemini
    from recruitai.config import Settings
    from recruitai.core.auth import CurrentUser
    from recruitai.core.tenancy import get_org_context
    from recruitai.modules.cvreview import service
    from recruitai.modules.cvreview.blocks import split_blocks

    settings = Settings(  # type: ignore[call-arg]
        llm_provider="gemini",
        google_genai_use_vertexai=True,
        ai_call_timeout_s=120.0,
        ai_daily_quota_per_user=100,
    )
    ctx = await get_org_context(
        CurrentUser(firebase_uid=f"uid-live-{uuid4().hex[:8]}", email="l@example.test"),
        db,
        x_org_id=None,
    )
    llm = gemini.GeminiGateway(
        client=gemini.build_client(settings),
        settings=settings,
        db=db,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    row = await service.evaluate(
        db, llm, org_id=ctx.org_id, language="en", track=track, level=level,
        source=(split_blocks(cv_text)[0], 1, None, False), parent_id=None,
    )  # fmt: skip
    return {"score": row.score, **row.data}


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM") != "1", reason="set RUN_LIVE_LLM=1")
@pytest.mark.parametrize("name", list(GOLDEN))
async def test_live_review(db_session, name):
    g = GOLDEN[name]
    cv = (HERE / g["file"]).read_text()
    out = await _run_service(db_session, cv, g["track"], g["level"])
    comments, blocks = out["comments"], out["blocks"]
    m = {
        "citation_validity": citation_validity(comments, blocks),
        "unsupported_rate": unsupported_rate(comments),
        "criterion_valid": criterion_valid_rate(comments, set(CRITERIA)),
        "criterion_accuracy": criterion_accuracy(comments, g, blocks),
        "recall": recall_of_flags(comments, g, blocks),
    }
    bad = next((c for c in comments if c["rating"] != "good"), None)
    sample = bad and {k: bad[k] for k in ("criterion", "rating", "why")} | {
        "quotes": [q["quote"] for q in bad["citations"]]}  # fmt: skip
    print(
        f"\n[cvreview:{name}] score={out['score']} band={g['band']} "
        f"grounding={out['grounding_rate']:.2f} comments={len(comments)} "
        + " ".join(f"{k}={v:.2f}" for k, v in m.items())
        + f"\n  sample={sample}"
    )
    assert band_ok(out["score"], g["band"]), f"score {out['score']} outside {g['band']}"
    assert out["grounding_rate"] >= 0.9, "service grounding_rate < 0.9"
    assert m["criterion_valid"] == 1.0, (
        "comment with a criterion outside checks.CRITERIA"
    )
    assert m["citation_validity"] == 1.0, (
        "a citation is not an exact substring of its block"
    )
    assert m["unsupported_rate"] <= 0.1, "poor/moderate comments without citation > 10%"
    assert m["criterion_accuracy"] >= 0.7, "criterion accuracy < 0.7"
    assert m["recall"] >= 0.6, "must_flag recall < 0.6"
    assert not invented_numbers([c["rewrite"] for c in comments if c["rewrite"]], cv)
    assert not explanation_problems(out)
