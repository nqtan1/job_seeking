"""Rule-based clean-up of an LLM-extracted ``JobPosition`` (ported from the legacy
``application/jobs/analysis/parser.py``). A small model often leaves location, contract,
salary or experience empty even when the text states them; these regexes fill the gaps.

Not ported: the "create sub-model if None" and "split a string into a list" steps (the typed
schema makes both impossible now). Fixed from the legacy: the K€ regex had a literal
backslash (``\\\\.``), and deduplicating ``benefits`` crashed when it was ``None``.
"""

import hashlib
import re

from recruitai.modules.jobs.schemas import CompensationInfo, JobPosition

_CITIES = (
    "Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|"
    "Rennes|Reims|Le Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Villeurbanne"
)


def clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = re.sub(r"^\s*[-•*]\s*", "", text.strip()).strip(" .-; ")  # noqa: B005  (a character set, on purpose)
    return cleaned or None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def post_process(job: JobPosition, text: str) -> JobPosition:
    job.job_description_text = text
    # Always ours: a hash the model made up would never match the text.
    job.source_meta.apply_url = None  # only providers know the real link
    job.source_meta.raw_description_hash = hashlib.sha256(text.encode()).hexdigest()
    job.title = clean_text(job.title) or job.title
    job.company.name = clean_text(job.company.name) or job.company.name
    badges = job.badges

    if not badges.location:
        # Case-sensitive whole words ("Nice to have" is not the city); two different cities
        # in one ad is ambiguous, so leave it empty rather than guess.
        found = {m.group(1) for m in re.finditer(rf"\b({_CITIES})\b(?! to have)", text)}
        if len(found) == 1:
            badges.location = found.pop()
            m = re.search(rf"\b{badges.location}\b[\s-]*(\d{{2,5}})", text)
            if m:
                badges.location_full = f"{badges.location} {m.group(1)}"
        elif badges.location_full:
            badges.location = clean_text(badges.location_full.split(",")[0])

    if not badges.contract_type:
        found_contracts = {
            m.group(0).upper()
            for m in re.finditer(
                r"\b(CDI|CDD|Freelance|Alternance|Stage|Apprentissage)\b",
                text,
                re.IGNORECASE,
            )
        }
        if (
            len(found_contracts) == 1
        ):  # "CDI ... Stage possible" is ambiguous: don't guess
            name = found_contracts.pop()
            badges.contract_type = name if name in ("CDI", "CDD") else name.capitalize()

    if not badges.salary:
        comp = job.compensation or CompensationInfo()
        if m := re.search(
            r"TJM[\s:=]?\s*(\d{2,4})\s*€\s*(?:/jour|par jour)?", text, re.IGNORECASE
        ):
            badges.salary = f"{m.group(1)}€/day"
            comp.salary_frequency = "Daily"  # same vocabulary as the extraction prompt
        elif m := re.search(
            r"(?<![\d.,])(\d{2,3}(?:[.,]\d)?)\s*K€", text, re.IGNORECASE
        ):
            value = int(float(m.group(1).replace(",", ".")) * 1000)
            badges.salary = f"{value}€/year"
            comp.salary_frequency = "Annuel"
        elif m := re.search(
            r"(\d{5,6})\s*€\s*(?:/an|par an|brut)", text, re.IGNORECASE
        ):
            badges.salary = f"{m.group(1)}€/year"
            comp.salary_frequency = "Annuel"
        if badges.salary:
            job.compensation = comp

    if not badges.experience_level and job.profile.experience:
        m = re.search(
            r"junior|confirmé|sénior|senior|lead|manager|expert",
            job.profile.experience,
            re.IGNORECASE,
        )
        if m:
            badges.experience_level = m.group(0)
        elif re.search(
            r"\d+\s*ans d'expérience", job.profile.experience, re.IGNORECASE
        ):
            badges.experience_level = "Expérimenté"

    job.missions = _dedupe(job.missions)
    job.tech_stack = _dedupe(job.tech_stack)
    job.working_methods = _dedupe(job.working_methods)
    job.profile.technical_skills = _dedupe(job.profile.technical_skills)
    job.profile.soft_skills = _dedupe(job.profile.soft_skills)
    job.profile.nice_to_have = _dedupe(job.profile.nice_to_have)
    if job.compensation and job.compensation.benefits:
        job.compensation.benefits = _dedupe(job.compensation.benefits)
    return job
