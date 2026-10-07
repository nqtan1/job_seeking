"""Grounding check and quality panel (ARCHITECTURE.md §10.2), deterministic and free: no model
call, so it can run on every edit. Pure functions over the letter, the Master profile and
the job.

Grounding flags what a reader would take as fact but the profile does not support: a known
technology that is not in the profile, a number that appears nowhere in it, an employer name
(introduced by "chez", "at"...) the profile and job never mention. These are warnings to highlight, not proof of a lie (the
profile can be incomplete), and the matching is by exact token, so it errs towards flagging.
"""

import json
import re
import unicodedata
from typing import Any

from recruitai.modules.letters.schemas import (
    KeywordCoverage,
    LetterCheck,
    LetterContent,
    LetterQuality,
    UnsupportedClaim,
)

TARGET_WORDS = {"short": 150, "standard": 250, "detailed": 350}
TARGET_TOLERANCE = 0.35
LONG_SENTENCE_WORDS = 30
REPEAT_THRESHOLD = 4

# Technologies a letter might invent. Ambiguous words ("go", "r", "swift" as an adjective) are
# left out on purpose: a false flag on an ordinary word is worse than a missed one.
_TECH = frozenset(
    [
        "python",
        "java",
        "javascript",
        "typescript",
        "react",
        "angular",
        "vue",
        "node",
        "nodejs",
        "django",
        "flask",
        "fastapi",
        "spring",
        "kotlin",
        "scala",
        "golang",
        "rust",
        "php",
        "ruby",
        "rails",
        "docker",
        "kubernetes",
        "terraform",
        "ansible",
        "jenkins",
        "aws",
        "azure",
        "gcp",
        "linux",
        "postgresql",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "kafka",
        "spark",
        "hadoop",
        "airflow",
        "tensorflow",
        "pytorch",
        "pandas",
        "numpy",
        "sql",
        "graphql",
        "git",
        "devops",
        "scrum",
        "tableau",
        "powerbi",
        "excel",
        "sap",
        "salesforce",
        "figma",
        "laravel",
        "symfony",
        "elasticsearch",
        "rabbitmq",
        "nginx",
        "bash",
        "matlab",
        "html",
        "css",
        "openshift",
        "gitlab",
        "github",
        "snowflake",
        "databricks",
        "dbt",
    ]
)
# An employer is introduced by a cue ("Chez Google", "at Acme"). Flagging every unseen
# capitalized word instead fired on translations of profile terms ("Informatique" for
# "Computer Science") in every live run, so names are only checked after a cue.
_EMPLOYER = re.compile(
    r"(?i:\b(?:chez|at|pour|au sein de|within|joined|rejoint|rejoindre))\s+"
    r"([A-Z][\w&'’.\-]*(?:\s+[A-Z][\w&'’.\-]*)*)"
)
_STOPWORDS = frozenset(
    [
        "avec",
        "dans",
        "pour",
        "cette",
        "comme",
        "votre",
        "notre",
        "leurs",
        "entre",
        "aussi",
        "mais",
        "plus",
        "tout",
        "tous",
        "sous",
        "ainsi",
        "alors",
        "afin",
        "chez",
        "depuis",
        "vers",
        "cela",
        "celui",
        "celle",
        "ceux",
        "elles",
        "nous",
        "vous",
        "that",
        "this",
        "with",
        "have",
        "from",
        "they",
        "will",
        "would",
        "about",
        "their",
        "there",
        "which",
        "where",
        "while",
        "other",
        "these",
        "those",
        "been",
        "being",
        "your",
        "what",
        "when",
        "more",
        "some",
        "such",
        "than",
        "then",
        "them",
        "into",
        "over",
        "also",
        "just",
        "very",
    ]
)
_CLICHES = (
    "je me permets de", "dynamique et motive", "esprit d'equipe", "team player",
    "force de proposition", "a l'ecoute", "forte motivation", "tres motive",
    "passionne par", "depuis toujours", "think outside the box", "hard-working",
    "hard working", "detail-oriented", "results-driven", "go-getter", "fast learner",
    "i am writing to apply", "perfect candidate", "dream job", "synergy",
)  # fmt: skip

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#]*(?:[.'’\-][A-Za-zÀ-ÿ0-9+#]+)*")
# Thousands groups are exactly 3 digits ("1 200", "45.000"), so "2019, 2020" stays two numbers.
_NUMBER = re.compile(r"\d+(?:[\u202f\xa0 .,]\d{3}(?!\d))*(?:[.,]\d+)?%?")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def norm(text: str) -> str:
    """Lowercase, accent-free, with typographic apostrophes straightened."""
    text = text.replace("’", "'").replace(" ", " ")
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


def _tokens(text: str) -> set[str]:
    return {t.rstrip(".'-") for t in _TOKEN.findall(norm(text))}


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _letter_text(c: LetterContent) -> str:
    """What the reader reads as claims: the subject and the prose, not the address block."""
    return "\n".join([c.subject, c.opening, *c.body, c.closing])


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _corpus(profile: dict[str, Any], job: dict[str, Any]) -> str:
    return json.dumps([profile, job], ensure_ascii=False)


def unsupported_claims(
    c: LetterContent, profile: dict[str, Any], job: dict[str, Any]
) -> list[UnsupportedClaim]:
    known = _tokens(_corpus(profile, job))
    known_numbers = {_digits(n) for n in _NUMBER.findall(_corpus(profile, job))}
    claims: dict[tuple[str, str], UnsupportedClaim] = {}

    def flag(term: str, kind: str, sentence: str) -> None:
        claims.setdefault(
            (kind, norm(term)),
            UnsupportedClaim(term=term, kind=kind, sentence=sentence),  # type: ignore[arg-type]
        )

    for sentence in _sentences(_letter_text(c)):
        for number in _NUMBER.findall(sentence):
            digits = _digits(number)
            if (
                len(digits) >= 2 or number.endswith("%")
            ) and digits not in known_numbers:
                flag(number.strip(), "number", sentence)
        for raw in _TOKEN.findall(sentence):
            token = norm(raw).rstrip(".'-")
            if token in _TECH and token not in known:
                flag(raw, "skill", sentence)
        for match in _EMPLOYER.finditer(sentence):
            name = match.group(1).rstrip(".,'-")
            if not _tokens(name) <= known:
                flag(name, "name", sentence)
    return list(claims.values())


def keyword_coverage(
    c: LetterContent, profile: dict[str, Any], job: dict[str, Any]
) -> KeywordCoverage:
    wanted = [
        *(job.get("tech_stack") or []),
        *((job.get("profile") or {}).get("technical_skills") or []),
        *((job.get("profile") or {}).get("nice_to_have") or []),
    ]
    text = norm(_letter_text(c))
    covered: list[str] = []
    missing: list[str] = []
    for keyword in dict.fromkeys(k.strip() for k in wanted if k and k.strip()):
        pattern = rf"(?<![a-z0-9]){re.escape(norm(keyword))}(?![a-z0-9])"
        (covered if re.search(pattern, text) else missing).append(keyword)
    total = len(covered) + len(missing)
    return KeywordCoverage(
        covered=covered,
        missing=missing,
        ratio=round(len(covered) / total, 2) if total else None,
    )


def quality(
    c: LetterContent, profile: dict[str, Any], job: dict[str, Any], length: str
) -> LetterQuality:
    text = _letter_text(c)
    words = [w for w in _TOKEN.findall(text)]
    target = TARGET_WORDS[length]
    sentence_lengths = [len(_TOKEN.findall(s)) for s in _sentences(text)]
    counts: dict[str, int] = {}
    for word in words:
        n = norm(word)
        if len(n) >= 5 and n not in _STOPWORDS:
            counts[n] = counts.get(n, 0) + 1
    normalized = norm(text)
    return LetterQuality(
        keyword_coverage=keyword_coverage(c, profile, job),
        word_count=len(words),
        target_words=target,
        within_target=abs(len(words) - target) <= target * TARGET_TOLERANCE,
        cliches=[x for x in _CLICHES if x in normalized],
        avg_sentence_words=round(sum(sentence_lengths) / len(sentence_lengths), 1)
        if sentence_lengths
        else 0.0,
        long_sentences=sum(1 for n in sentence_lengths if n > LONG_SENTENCE_WORDS),
        repeated_words=dict(
            sorted(
                ((w, n) for w, n in counts.items() if n >= REPEAT_THRESHOLD),
                key=lambda item: -item[1],
            )
        ),
    )


def check(
    c: LetterContent, profile: dict[str, Any], job: dict[str, Any], length: str
) -> LetterCheck:
    return LetterCheck(
        unsupported_claims=unsupported_claims(c, profile, job),
        quality=quality(c, profile, job, length),
    )
