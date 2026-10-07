"""Grounding check and quality panel (P2-22): fixture profiles and letters, no model."""

from recruitai.modules.letters.quality import (
    check,
    keyword_coverage,
    unsupported_claims,
)
from recruitai.modules.letters.schemas import Header, LetterContent, Recipient

PROFILE = {
    "personal_info": {"name": "Lucas Martel", "email": "lucas@example.test"},
    "formations": [
        {"degree": "Bachelor", "field": "Computer Science", "institution": "Lyon 1"}
    ],
    "experiences": [
        {
            "job_title": "Software Development Intern",
            "company": "Brightwave SAS",
            "start_date": "June 2023",
            "end_date": "September 2023",
            "description": "REST endpoints with Flask, unit tests with pytest, fixed 25 bugs",
        }
    ],
    "skills": [
        {"name": "Python"},
        {"name": "Flask"},
        {"name": "SQL"},
        {"name": "Docker"},
    ],
}
JOB = {
    "title": "Développeur Python",
    "company": {"name": "Acme"},
    "badges": {"location": "Lyon"},
    "tech_stack": ["Python", "FastAPI", "Docker"],
    "profile": {"technical_skills": ["SQL"], "nice_to_have": []},
}


def letter(opening: str, *body: str, closing: str = "Cordialement.") -> LetterContent:
    return LetterContent(
        header=Header(name="Lucas Martel"),
        recipient=Recipient(company="Acme"),
        subject="Candidature Développeur Python",
        salutation="Madame, Monsieur,",
        opening=opening,
        body=list(body),
        closing=closing,
        signature="Lucas Martel",
    )


GROUNDED = letter(
    "Je candidate au poste de développeur Python chez Acme.",
    "Chez Brightwave SAS, j'ai corrigé 25 bugs avec Python et Flask, et écrit des tests pytest.",
    "Je maîtrise SQL et Docker.",
)
INVENTED = letter(
    "Je candidate au poste de développeur Python.",
    "Chez Google, j'ai piloté un cluster Kubernetes et réduit les coûts de 40% grâce à Terraform.",
)


def test_a_letter_that_sticks_to_the_profile_is_not_flagged():
    assert unsupported_claims(GROUNDED, PROFILE, JOB) == []


def test_an_invented_skill_number_and_employer_are_flagged_with_their_sentence():
    flags = {
        (c.kind, c.term): c.sentence for c in unsupported_claims(INVENTED, PROFILE, JOB)
    }
    assert {k for k in flags} == {
        ("name", "Google"),
        ("skill", "Kubernetes"),
        ("skill", "Terraform"),
        ("number", "40%"),
    }
    assert all("Google" in s for s in flags.values())  # the sentence to highlight


def test_skills_in_the_job_posting_but_not_the_profile_are_not_treated_as_invented():
    only_in_job = letter("Je connais FastAPI.", "Et j'apprends vite.")
    job = {**JOB, "tech_stack": ["Python", "FastAPI"]}
    assert (
        unsupported_claims(only_in_job, PROFILE, job) == []
    )  # FastAPI is the job's own word


def test_keyword_coverage_lists_covered_and_missing_job_keywords():
    cov = keyword_coverage(GROUNDED, PROFILE, JOB)
    assert cov.covered == ["Python", "Docker", "SQL"] and cov.missing == ["FastAPI"]
    assert cov.ratio == 0.75
    assert (
        keyword_coverage(GROUNDED, PROFILE, {}).ratio is None
    )  # no keywords, no ratio


def test_quality_panel_reports_length_cliches_readability_and_repeated_words():
    long_sentence = " ".join(["mot"] * 35) + "."
    text = letter(
        "Je me permets de postuler. Passionné par le développement.",
        "Le développement logiciel, le développement web, le développement mobile, "
        "le développement cloud. " + long_sentence,
        closing="Cordialement.",
    )
    q = check(text, PROFILE, JOB, "short").quality
    assert q.target_words == 150 and q.word_count > 40 and q.within_target is False
    assert q.cliches == ["je me permets de", "passionne par"]
    assert q.long_sentences == 1 and q.avg_sentence_words > 5
    assert q.repeated_words == {"developpement": 5}

    ok = check(GROUNDED, PROFILE, JOB, "short").quality
    assert ok.cliches == [] and ok.repeated_words == {} and ok.long_sentences == 0


def test_translated_profile_terms_and_known_employers_are_not_flagged_as_names():
    translated = letter(
        "Après mon diplôme en Sciences de l'Informatique, j'ai rejoint Brightwave SAS.",
        "Chez Acme, je ferai du génie logiciel en Python à Lyon.",
    )
    # "Informatique"/"Logiciel" are translations, not claims; Brightwave SAS is in the profile
    assert unsupported_claims(translated, PROFILE, JOB) == []
    invented = letter("J'ai travaillé chez Google Cloud France et at Initech.")
    names = {
        c.term for c in unsupported_claims(invented, PROFILE, JOB) if c.kind == "name"
    }
    assert names == {"Google Cloud France", "Initech"}


def test_adjacent_numbers_stay_separate_and_a_cue_must_be_a_whole_word():
    profile = {
        **PROFILE,
        "experiences": [{"description": "2019 2020 2021, 20 30 40 users"}],
    }
    listed = letter("Between 2019, 2020 and 2021, projects of 20, 30, 40 users.")
    assert (
        unsupported_claims(listed, profile, JOB) == []
    )  # each number is in the profile

    invented = letter("Projects of 2019, 777 users.")
    assert [c.term for c in unsupported_claims(invented, profile, JOB)] == ["777"]

    not_a_cue = letter("I saw what Google does and that Mistral model.")
    assert [
        c.kind for c in unsupported_claims(not_a_cue, PROFILE, JOB) if c.kind == "name"
    ] == []
    cue = letter("I worked at Google.")
    assert [(c.kind, c.term) for c in unsupported_claims(cue, PROFILE, JOB)] == [
        ("name", "Google")
    ]
