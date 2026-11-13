"""The CV rubric, rule-based signals, dimension scores and the grounding of the model's comments (no
LLM, no I/O). Rubric = one source of truth: the prompt lists it, ``Criterion`` (schemas) restricts the
model to it, rule tags map onto it and the web shows it next to each comment. Sources (shown by the
web): Tech Interview Handbook resume guide, Google XYZ formula (L. Bock), InfoWorld resume dos and don'ts.
The LLM adds scope/stack/projects/progression; code never trusts what it did not copy."""

import re
import unicodedata

from recruitai.modules.cvreview.schemas import (
    MAX_CHARS,
    Block,
    BlockComment,
    Criterion,
    Quote,
    Rating,
)

_UNIT = r"ms|s|sec|seconds?|minutes?|hours?|days?|[kmgt]b|rps|qps|users?|customers?|requests?|services?|engineers?|clients?|records?|events?"
# criterion id -> (dimension, what good looks like)
CRITERIA: dict[str, tuple[str, str]] = {
    "impact.metric": ("impact", "States a measurable result (number, %, scale, latency, cost, users): Google XYZ formula 'accomplished X, as measured by Y, by doing Z'."),
    "impact.outcome": ("impact", "Describes the outcome the candidate produced, not a duty or a responsibility ('responsible for', 'helped', 'worked on')."),
    "scope.ownership": ("scope", "Shows what the candidate owned: a feature, service or system, team size, users, traffic or data volume."),
    "scope.level_fit": ("scope", "Scope and independence match the target level (intern/junior: small owned scope; senior/staff: architecture, trade-offs, cross-team influence)."),
    "stack.named": ("stack", "Names specific tools and versions in context ('PostgreSQL and Redis', not 'various databases'), relevant to the track."),
    "projects.depth": ("projects", "Each project states the candidate's own contribution and result, links to a repo or demo, and is not a tutorial clone."),
    "skills.evidence": ("skills_ats", "Skills are grouped, use standard names, and are backed by evidence in the experience or projects."),
    "structure.format": ("structure", "Standard section headings, sensible order for the level, short enough (1 page, 2 for senior), parseable text."),
    "language.concise": ("language", "Concise active voice that opens with an action verb; no buzzwords, no first person, bullets short enough to scan."),
    "progression.growth": ("progression", "Career shows growing responsibility, dates that add up, no unexplained gap or overlap."),
    "credibility.links": ("credibility", "Contact details and verifiable public work (GitHub, LinkedIn, portfolio) are present; claims match the seniority."),
}  # fmt: skip

# rule tag (checks.signals) -> the criterion it is evidence for
TAG_CRITERION: dict[str, Criterion] = {
    "no_metric": "impact.metric",
    "weak_verb": "impact.outcome",
    "buzzword": "language.concise",
    "first_person": "language.concise",
    "too_long": "language.concise",
}

RUBRIC_TEXT = "\n".join(f"- {k}: {v[1]}" for k, v in CRITERIA.items())

METRIC = re.compile(
    rf"[$€£]\s?\d|\d\s?(?:%|[kKMBx]\b)|\b\d{{1,3}}(?:[,. ]\d{{3}})+\b|\b\d+\s?(?:{_UNIT})\b"
    r"|\b(?:halved|doubled|tripled|divided)\b",
    re.IGNORECASE,
)
WEAK = re.compile(
    r"\b(responsible for|helped|worked on|assisted|participated|involved in|tasked with|"
    r"in charge of|duties included|responsable de|aidé|participé|contribué à|chargé de)\b",
    re.IGNORECASE,
)
BUZZ = re.compile(
    r"\b(results[- ]driven|team player|passionate|hard[- ]working|dynamic|self[- ]starter|"
    r"go-getter|detail[- ]oriented|motivated|synergy|rockstar|ninja|think outside|"
    r"passionné|dynamique|motivé|esprit d'équipe|rigoureux)\b",
    re.IGNORECASE,
)
FIRST_PERSON = re.compile(r"\b(i|my|me)\b", re.IGNORECASE)
TOO_LONG = 230
_CONTENT = ("experience", "projects")
_LINKS = ("github.com", "gitlab.com", "linkedin.com")

_DIMS = ("impact", "scope", "stack", "projects", "skills_ats", "structure", "progression", "language", "credibility")  # fmt: skip
# per level, the weight (sum 100) of each of _DIMS; an intern is judged on projects, a senior on scope
WEIGHTS: dict[str, dict[str, int]] = {
    lvl: dict(zip(_DIMS, w, strict=True))
    for lvl, w in {
        "intern": (10, 15, 12, 22, 10, 10, 8, 8, 5),
        "junior": (20, 15, 12, 12, 10, 10, 8, 8, 5),
        "mid": (20, 15, 12, 12, 10, 10, 8, 8, 5),
        "senior": (18, 23, 11, 11, 9, 9, 7, 7, 5),
        "staff": (18, 23, 11, 11, 9, 9, 7, 7, 5),
    }.items()
}  # fmt: skip


def signals(block: Block) -> list[str]:
    if block.kind == "heading":
        return []
    t, tags = block.text, []
    if block.kind == "bullet" and block.section in _CONTENT and not METRIC.search(t):
        tags.append("no_metric")
    for tag, rx in (
        ("weak_verb", WEAK),
        ("buzzword", BUZZ),
        ("first_person", FIRST_PERSON),
    ):
        if rx.search(t):
            tags.append(tag)
    if len(t) > TOO_LONG:
        tags.append("too_long")
    return tags


def rule_dimensions(blocks: list[Block]) -> dict[str, float]:
    text = "\n".join(b.text for b in blocks)
    low = text.lower()
    body = [b for b in blocks if b.kind != "heading"]
    sections = {b.section for b in blocks if b.kind == "heading"}
    words = len(text.split())

    structure = 60 * len(sections & {"experience", "education", "skills"}) / 3
    structure += 40 if 200 <= words <= 900 else 20 if 100 <= words else 0

    skills_ats = 30.0
    if "skills" in sections:
        used = "\n".join(b.text for b in blocks if b.section in _CONTENT).lower()
        toks = {
            t.strip().lower()
            for b in blocks
            if b.section == "skills" and b.kind != "heading"
            for t in re.split(r"[,;|•/]|\s-\s", b.text.split(":", 1)[-1])
            if 1 < len(t.strip()) <= 30
        }
        unused = sum(t not in used for t in toks) / len(toks) if toks else 1
        skills_ats = 40 + 60 * (1 - unused)

    n = max(len(body), 1)
    buzz = sum(bool(BUZZ.search(b.text)) for b in body) / n
    bullets = [b for b in body if b.kind == "bullet"]
    long_ = sum(len(b.text) > TOO_LONG for b in bullets) / max(len(bullets), 1)
    language = max(0.0, 100 - 200 * buzz - 100 * long_)

    credibility = min(100, 20 + 40 * sum(k in low for k in _LINKS))

    impact_b = [b for b in bullets if b.section in _CONTENT]
    impact = (
        100 * sum(bool(METRIC.search(b.text)) for b in impact_b) / len(impact_b)
        if impact_b
        else 0
    )

    return {
        "structure": structure,
        "skills_ats": skills_ats,
        "language": language,
        "credibility": credibility,
        "impact": impact,
    }


def overall(dim_scores: dict[str, float], level: str) -> int:
    w = {k: v for k, v in WEIGHTS[level].items() if k in dim_scores}
    total = sum(w.values())
    return round(sum(dim_scores[k] * v for k, v in w.items()) / total) if total else 0


_COMMENTED = {"summary", "experience", "projects", "skills", "education"}
_THOUSANDS = re.compile(r"(?<=\d)[,. ](?=\d{3}\b)")
MAX_CITES = 5
MIN_EVIDENCE = 8  # a 1-letter "quote" is a substring of anything
_TAGS = {  # signal -> (why, fix)
    "no_metric": ("No number or measurable result.", "add a measurable outcome"),
    "weak_verb": ("Describes a duty, not an outcome.", "replace the weak phrase by what you did and achieved"),
    "buzzword": ("Uses a buzzword instead of evidence.", "replace the buzzword by a concrete fact"),
    "first_person": ("Written in the first person.", "drop the pronoun"),
    "too_long": ("Too long to scan quickly.", "shorten to one line"),
}  # fmt: skip


def _numbers(t: str) -> set[str]:
    return set(re.findall(r"\d+", _THOUSANDS.sub("", t)))


def dimension_blocks(
    blocks: list[Block], tags: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Per dimension, the blocks whose rule tags lower it (tag -> criterion -> dimension)."""
    out: dict[str, list[str]] = {}
    for b in blocks:
        for dim in {CRITERIA[TAG_CRITERION[t]][0] for t in tags[b.id]}:
            out.setdefault(dim, []).append(b.id)
    return out


def _rule_comment(b: Block, tags: list[str]) -> BlockComment:
    """Fallback for a block the model skipped, so the UI never shows an uncommented block."""
    rating: Rating = "good" if not tags else "moderate" if len(tags) == 1 else "poor"
    return BlockComment(
        block_id=b.id,
        # no tag: the checks that found nothing are verb/length/buzzword ones, i.e. language
        criterion=TAG_CRITERION[tags[0]] if tags else "language.concise",
        citations=[Quote(block_id=b.id, quote=b.text)] if tags else [],
        why=" ".join(_TAGS[t][0] for t in tags) or "No weak signal found by the automatic checks.",
        improve=("Fix: " + "; ".join(_TAGS[t][1] for t in tags) + ".") if tags else None,
        rewrite=None,
        rating=rating,
        source="rule",
    )  # fmt: skip


_PUNCT = str.maketrans("‘’“”–—", "''\"\"--")


def _fold(s: str) -> tuple[str, list[tuple[int, int]]]:
    """NFKC + ASCII quotes/dashes + collapsed whitespace, with the original span of each char."""
    clusters: list[
        tuple[str, int, int]
    ] = []  # (raw, start, end): base char + its accents
    for i, c in enumerate(s):
        if clusters and (
            unicodedata.combining(c) or (c.isspace() and clusters[-1][0].isspace())
        ):
            clusters[-1] = (clusters[-1][0] + c, clusters[-1][1], i + 1)
        else:
            clusters.append((c, i, i + 1))
    text, spans = "", []
    for raw, a, b in clusters:
        f = (
            " "
            if raw.isspace()
            else unicodedata.normalize("NFKC", raw).translate(_PUNCT)
        )
        text += f
        spans += [(a, b)] * len(f)
    return text, spans


def _locate(q: Quote, by_id: dict[str, Block]) -> Quote | None:
    """The quote as the exact substring of its own block (unicode/whitespace-tolerant), else None."""
    b = by_id.get(q.block_id)
    if b is None or len(q.quote) > 2 * MAX_CHARS:  # a block holds <= MAX_CHARS
        return None
    fq = _fold(q.quote)[0].strip()
    fb, spans = _fold(b.text)
    if not fq or (len(fq) < MIN_EVIDENCE and fq != fb.strip()):
        return None
    i = fb.find(fq)
    if i < 0:
        return None
    return Quote(
        block_id=q.block_id, quote=b.text[spans[i][0] : spans[i + len(fq) - 1][1]]
    )


def ground(
    comments: list[BlockComment], blocks: list[Block], tags: dict[str, list[str]]
) -> tuple[list[BlockComment], float]:
    """One comment per content block, in block order, plus the share of citations that verified.
    Unknown/duplicate ids are dropped; each citation is relocated to the exact text of its block
    or dropped; rewrites with a number that is not in the original block are nulled."""
    content = [b for b in blocks if b.kind != "heading" and b.section in _COMMENTED]
    by_id = {b.id: b for b in content}
    kept: dict[str, BlockComment] = {}
    given = verified = 0
    for c in comments:
        b = by_id.get(c.block_id)
        if b is None or c.block_id in kept:
            continue
        located = (_locate(q, by_id) for q in c.citations[:MAX_CITES])
        cites = list({(q.block_id, q.quote): q for q in located if q}.values())
        given += len(c.citations[:MAX_CITES])
        verified += len(cites)
        rewrite = (
            None if c.rewrite and _numbers(c.rewrite) - _numbers(b.text) else c.rewrite
        )
        kept[c.block_id] = c.model_copy(
            update={  # the model's output is capped here: it is stored and shown as is
                "citations": cites,
                "source": "ai",
                "rewrite": rewrite and rewrite[:MAX_CHARS],
                "why": c.why[:MAX_CHARS],
                "improve": c.improve and c.improve[:MAX_CHARS],
            }
        )
    return [kept.get(b.id) or _rule_comment(b, tags[b.id]) for b in content], (
        verified / given if given else 1.0
    )
