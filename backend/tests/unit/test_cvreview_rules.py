from typing import get_args

import pytest
from pydantic import ValidationError

from recruitai.modules.cvreview import checks, schemas
from recruitai.modules.cvreview.blocks import extract_text, split_blocks
from recruitai.modules.cvreview.checks import (
    METRIC,
    WEIGHTS,
    _locate,
    dimension_blocks,
    ground,
    overall,
    rule_dimensions,
    signals,
)
from recruitai.modules.cvreview.schemas import (
    MAX_BLOCKS,
    Block,
    BlockComment,
    Quote,
    RecheckIn,
)

WEAK = """Jane Doe
jane@example.com

Experience
Software Developer, Acme   Jan 2018 - Mar 2019
- Responsible for the backend of the website
- Results-driven team player who worked on many things and helped the team with
  various tasks in the company over a long period of time
Developer, Beta   Dec 2020 - Present
* I did some coding

Skills
Kubernetes, Rust, Python
"""

STRONG = """Jane Doe
github.com/jane | linkedin.com/in/jane

Summary
Backend engineer focused on data pipelines.

Experience
Software Engineer, Acme   Jan 2018 - Mar 2020
- Reduced API p95 latency by 40% by caching hot queries in Redis
- Built an ingestion service handling 2M events/day with Python and Kafka
Senior Engineer, Beta   Apr 2020 - Present
- Led migration of 12 services to Kubernetes, cutting infra cost by $30k per year

Projects
- Shipped an open-source CLI with 1.5k GitHub stars

Skills
Python, Kafka, Redis, Kubernetes

Education
MSc Computer Science
"""


def blocks_of(text):
    return split_blocks(text)[0]


def test_split_blocks_sections_and_wrapping():
    bs = blocks_of(WEAK)
    assert [b.id for b in bs][:2] == ["b1", "b2"]
    assert bs[0].section == "header"
    assert bs[4].kind == "bullet" and bs[4].section == "experience"
    wrapped = next(b for b in bs if b.text.startswith("Results-driven"))
    assert "various tasks" in wrapped.text  # continuation line joined
    assert bs[-1].section == "skills"
    assert len(split_blocks("- x\n" * 400)[0]) == MAX_BLOCKS
    assert split_blocks("- x\n" * 400)[1] and not split_blocks(WEAK)[1]
    assert len(blocks_of("- " + "a" * 2000)[0].text) == 600


def test_split_blocks_edge_cases():
    assert [b.text for b in blocks_of("Experience\n•\n- Built a thing")] == [
        "Experience",
        "Built a thing",
    ]  # lone glyph skipped, no crash
    bs = blocks_of("Experience\n- Built an API\nSenior Engineer, Beta 2020")
    assert [b.kind for b in bs] == ["heading", "bullet", "text"]  # title not glued
    assert blocks_of("Experience\n- Built an API,\nand a cache")[1].text.endswith(
        "and a cache"
    )
    assert blocks_of("\uf0b7 Built an API")[0].kind == "bullet"
    vi = blocks_of(
        "Nguyễn A\na@b.c\n\nKINH NGHIỆM LÀM VIỆC:\n● Xây dựng API\n— Kỹ năng —\nPython"
    )
    assert [b.section for b in vi] == [
        "header",
        "header",
        "experience",
        "experience",
        "skills",
        "skills",
    ]
    assert blocks_of("TECHNICAL SKILLS:\nGo")[0].section == "skills"
    assert blocks_of("Education & Certifications\nBSc")[0].section == "education"
    no_head = blocks_of(
        "Nguyễn A\na@b.c\n0900\nXây dựng API cho 3 khách hàng\nLàm việc nhóm"
    )
    assert [b.section for b in no_head] == ["header"] * 3 + ["experience"] * 2


def test_metric_regex():
    for yes in ("40%", "3x", "$2M", "1,200 users", "p95 120 ms"):
        assert METRIC.search(yes), yes
    for no in ("Python 3", "Java 8", "Node 18"):
        assert not METRIC.search(no), no


def test_extract_text():
    assert extract_text(b"hello", "text/plain") == ("hello", 1)
    assert extract_text(b"  ", "text/plain") is None
    assert extract_text(b"not a pdf", "application/pdf") is None


def test_signals():
    bs = {b.text[:12]: b for b in blocks_of(WEAK)}
    assert {"weak_verb", "no_metric"} <= set(signals(bs["Responsible "]))
    assert {"buzzword", "no_metric"} <= set(signals(bs["Results-driv"]))
    assert "first_person" in signals(bs["I did some c"])
    strong = next(b for b in blocks_of(STRONG) if b.text.startswith("Reduced"))
    assert signals(strong) == []


def test_weak_cv_scores_below_strong():
    weak, strong = (rule_dimensions(blocks_of(t)) for t in (WEAK, STRONG))
    assert strong["impact"] == 100 and weak["impact"] == 0
    assert strong["credibility"] > weak["credibility"]
    assert overall(strong, "mid") > overall(weak, "mid")


def test_weights_and_overall_renormalise():
    assert all(sum(w.values()) == 100 for w in WEIGHTS.values())
    assert WEIGHTS["intern"]["projects"] > WEIGHTS["mid"]["projects"]
    assert overall({"impact": 80, "structure": 80}, "mid") == 80  # missing dims skipped
    assert overall({}, "mid") == 0


def test_rubric_matches_criterion_literal():
    assert set(get_args(schemas.Criterion)) == set(checks.CRITERIA)
    assert set(checks.TAG_CRITERION.values()) <= set(checks.CRITERIA)


def _c(block_id, rating="poor", quotes=(), rewrite=None):
    return BlockComment(
        block_id=block_id, criterion="impact.metric", citations=[Quote(block_id=b, quote=q) for b, q in quotes],
        why="why", improve="fix", rewrite=rewrite, rating=rating,
    )  # fmt: skip


def test_ground_relocates_citations_drops_bad_ones_and_fills_skipped():
    blocks = [
        Block(id="b1", kind="heading", section="experience", text="EXPERIENCE"),
        Block(
            id="b2",
            kind="bullet",
            section="experience",
            text="Cut latency by  40%\nwith Redis",
        ),
        Block(
            id="b3", kind="bullet", section="experience", text="Helped with deployments"
        ),
        Block(id="b4", kind="bullet", section="experience", text="Built an API"),
        Block(id="b5", kind="bullet", section="skills", text="Go, Rust"),
    ]
    sig = {
        "b1": [],
        "b2": [],
        "b3": ["weak_verb", "no_metric"],
        "b4": ["no_metric"],
        "b5": [],
    }
    comments = [
        _c(
            "b2",
            "good",
            [
                ("b2", "latency by 40% with"),
                ("b5", "Rust"),
                ("b5", "Go, Rust"),
                ("b9", "Redis"),
            ],
            rewrite="Cut latency by [X%]",
        ),
        _c("b3", quotes=[("b3", "invented")], rewrite="Led deployments, 99% faster"),
        _c("b3", quotes=[("b3", "Helped")]),  # duplicate: first wins
        _c("b1"),  # heading: dropped
        _c("b99"),  # unknown: dropped
    ]

    out, rate = ground(comments, blocks, sig)

    assert [c.block_id for c in out] == ["b2", "b3", "b4", "b5"]
    # relocated to the block's exact text; "Rust" too short, but the whole block is fine; b9 unknown
    assert [(q.block_id, q.quote) for q in out[0].citations] == [
        ("b2", "latency by  40%\nwith"),
        ("b5", "Go, Rust"),
    ]
    assert out[0].rewrite == "Cut latency by [X%]"
    assert (
        out[1].citations == [] and out[1].rewrite is None
    )  # invented words and number
    skipped = out[2]  # rule comment: criterion from the first tag, whole block cited
    assert (skipped.rating, skipped.criterion, skipped.citations[0].quote) == (
        "moderate",
        "impact.metric",
        "Built an API",
    )
    assert out[3].criterion == "language.concise" and out[3].rating == "good"
    assert out[3].citations == [] and out[3].source == "rule" and out[0].source == "ai"
    assert rate == 2 / 5
    assert dimension_blocks(blocks, sig) == {"impact": ["b3", "b4"]}


def test_ground_rejects_thousands_trick_and_input_is_validated():
    blocks = [
        Block(
            id="b1",
            kind="bullet",
            section="experience",
            text="Served 1,200 users with low latency",
        )
    ]
    out, rate = ground(
        [_c("b1", quotes=[("b1", "a")], rewrite="Served 200 users")], blocks, {"b1": []}
    )
    assert (
        out[0].citations == [] and out[0].rewrite is None and rate == 0
    )  # 1-char quote, 200 != 1200

    def blk(i, text="x"):
        return {"id": i, "kind": "bullet", "section": "experience", "text": text}

    for bad in ([blk("b1"), blk("b1")], [blk("b1", "a\x00b")], [blk("zz")]):
        with pytest.raises(ValidationError):
            RecheckIn(blocks=bad, track="backend", level="mid")


def test_locate_is_unicode_tolerant_and_returns_the_original_text():
    def loc(text, quote):
        got = _locate(
            Quote(block_id="b1", quote=quote),
            {"b1": Block(id="b1", kind="bullet", section="experience", text=text)},
        )
        return got and got.quote

    assert (
        loc("Cr\u0065\u0301er un service", "Créer un service")
        == "Cre\u0301er un service"
    )  # NFD
    assert (
        loc("He said \u201cship it\u201d \u2014 done", 'said "ship it" - done')
        == "said \u201cship it\u201d \u2014 done"
    )
    assert (
        loc("Deployed \ufb01nal builds", "Deployed final builds")
        == "Deployed \ufb01nal builds"
    )  # ligature
    assert loc("Used C++ (v1.2) daily", "C++ (v1.2)") == "C++ (v1.2)"
    assert loc("Used C++ (v1.2) daily", "c++ (v1.2)") is None  # case-sensitive
    assert loc("Used Redis daily", "Redis") is None  # under 8 chars


def test_a_stored_v1_review_still_loads():
    """Reviews are read back through the current model: keep this row valid when the schema grows."""
    old = {
        "blocks": [{"id": "b1", "kind": "bullet", "section": "experience", "text": "Cut p95 by 40%"}],
        "comments": [{
            "block_id": "b1", "criterion": "impact.metric", "rating": "good", "why": "Has a number.",
            "citations": [{"block_id": "b1", "quote": "Cut p95 by 40%"}], "improve": None, "rewrite": None,
        }],
        "dimensions": {"impact": {"score": 90.0, "weight": 20.0}},
        "summary": {"strengths": [{"text": "Metrics", "block_id": "b1"}], "top_fixes": []},
        "pages": 1,
        "grounding_rate": 1.0,
    }  # fmt: skip
    assert schemas.ReviewData.model_validate(old).comments[0].source == "ai"
