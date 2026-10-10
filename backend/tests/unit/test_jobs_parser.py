"""jobs/parser.py (P2-08b): rule-based gap filling after LLM extraction."""

from recruitai.modules.jobs.parser import post_process
from recruitai.modules.jobs.schemas import JobPosition


def blank_job(**over) -> JobPosition:
    data = {
        "title": "- Dev Python ",
        "company": {"name": "Acme"},
        "badges": dict.fromkeys(
            ["contract_type", "location", "location_full", "remote_policy"]
            + ["experience_level", "salary"]
        ),
        "about_company": {},
        "missions": ["Build APIs", "Build APIs"],
        "tech_stack": [],
        "working_methods": [],
        "profile": {
            "experience": "3 à 5 ans d'expérience",
            "education": None,
            "technical_skills": ["Python", "Python"],
            "soft_skills": [],
            "nice_to_have": [],
        },
        "modalities": {},
        "source_meta": {},
    }
    return JobPosition.model_validate(data | over)


def test_fills_gaps_from_the_text_and_dedupes():
    text = "CDI à Lyon 69 - TJM: 550 € par jour. Équipe produit."
    job = post_process(blank_job(), text)
    assert job.title == "Dev Python"
    assert (job.badges.contract_type, job.badges.location) == ("CDI", "Lyon")
    assert job.badges.location_full == "Lyon 69"
    assert job.badges.salary == "550€/day"
    assert job.compensation and job.compensation.salary_frequency == "Daily"
    assert job.badges.experience_level == "Expérimenté"
    assert job.missions == ["Build APIs"] and job.profile.technical_skills == ["Python"]
    assert job.job_description_text == text and job.source_meta.raw_description_hash


def test_keeps_what_the_model_found_and_handles_k_euro_salary():
    job = blank_job()
    job.badges.contract_type = "CDD"
    out = post_process(job, "Salaire 45K€ par an, CDI possible")
    assert out.badges.contract_type == "CDD"  # never overwritten
    assert out.badges.salary == "45000€/year" and out.compensation is not None


def test_ambiguous_or_lookalike_matches_are_left_empty_not_guessed():
    text = (
        "Backend. Nice to have: Kubernetes. Stage de fin d'études possible, CDI visé."
    )
    out = post_process(blank_job(), text)
    assert out.badges.location is None  # "Nice to have" is not the city
    assert out.badges.contract_type is None  # CDI and Stage: ambiguous

    two_cities = post_process(blank_job(), "Postes à Paris et à Lyon, CDI.")
    assert (
        two_cities.badges.location is None and two_cities.badges.contract_type == "CDI"
    )

    odd = post_process(blank_job(), "Salaire 45.000K€ ou 45,5K€")
    assert odd.badges.salary == "45500€/year"  # never 1000x off
    assert post_process(blank_job(), "Salaire 45.000K€").badges.salary is None


def test_the_description_hash_is_always_the_real_one():
    job = blank_job(
        source_meta={
            "raw_description_hash": "made-up-by-the-model",
            "apply_url": "https://made.up",
        }
    )
    meta = post_process(job, "texte").source_meta
    assert meta.raw_description_hash != "made-up-by-the-model"
    assert meta.apply_url is None  # only providers set the apply link
