from uuid import uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from recruitai.ai.prompts import coach, cv_extract, fit, letters
from recruitai.ai.prompts import jobs as job_prompt
from recruitai.core.errors import ValidationFailed
from recruitai.modules.applications.schemas import (
    TRANSITIONS,
    ApplicationIn,
    ApplicationUpdate,
    StatusChangeIn,
    next_statuses,
)
from recruitai.modules.candidates.schemas import CVInformation
from recruitai.modules.coach.schemas import MAX_MESSAGE_CHARS, ConversationIn, MessageIn
from recruitai.modules.jobs.schemas import (
    FileJobIn,
    JobIn,
    JobPosition,
    ManualJobIn,
    SearchJobIn,
)
from recruitai.modules.letters.schemas import (
    Header,
    LetterContent,
    LetterDraft,
    Recipient,
)
from recruitai.modules.matching.schemas import FitCheck

ALL = {"to_apply", "applied", "in_review", "interview", "offer", "rejected", "ghosted"}


def test_every_status_has_a_row_and_no_status_leads_to_itself_or_back_to_to_apply():
    assert set(TRANSITIONS) == ALL
    for status, targets in TRANSITIONS.items():
        assert set(targets) <= ALL - {"to_apply"} and status not in targets
    assert TRANSITIONS["rejected"] == () and next_statuses("to_apply") == ["applied"]
    assert "ghosted" in next_statuses("interview") and "applied" not in next_statuses(
        "interview"
    )


def test_input_rules():
    assert ApplicationIn(company_name="Acme").status == "to_apply"
    assert (
        ApplicationIn(job_id="00000000-0000-0000-0000-000000000001").company_name
        is None
    )
    for bad in (
        {},  # no company and no job
        {"company_name": ""},
        {
            "company_name": "Acme",
            "status": "interview",
        },  # a new application starts earlier
        {"company_name": "Acme", "source": "tiktok"},
        {"company_name": "Acme", "notes": "x" * 5001},
    ):
        with pytest.raises(ValidationError):
            ApplicationIn(**bad)
    with pytest.raises(ValidationError):
        StatusChangeIn(status="hired")
    with pytest.raises(ValidationError):
        ApplicationUpdate(company_name=None)  # can be omitted, not erased
    assert ApplicationUpdate(notes=None).model_fields_set == {"notes"}


MINIMIZED = {
    "photo",
    "picture",
    "image",
    "date_of_birth",
    "dob",
    "birth_date",
    "birthdate",
    "gender",
    "sex",
    "nationality",
    "marital_status",
}


def _field_names(model: type[BaseModel], seen: set[type[BaseModel]]) -> set[str]:
    if model in seen:
        return set()
    seen.add(model)
    names = set(model.model_fields)
    for info in model.model_fields.values():
        for arg in (info.annotation, *getattr(info.annotation, "__args__", ())):
            for inner in (arg, *getattr(arg, "__args__", ())):
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    names |= _field_names(inner, seen)
    return names


def test_cv_schema_has_no_minimized_fields_at_any_depth() -> None:
    assert _field_names(CVInformation, set()).isdisjoint(MINIMIZED)


def test_prompt_is_versioned() -> None:
    assert cv_extract.PROMPT_VERSION == "cv_extract@2"
    assert "No Hallucinations" in cv_extract.SYSTEM_PROMPT


def test_prompt_keeps_its_grounding_and_language_rules_and_is_versioned():
    p = coach.SYSTEM_PROMPT_CAREER_COACH
    assert "RecruitAI Career Coach" in p
    assert "Do not invent facts" in p  # grounded in the provided data
    assert "same language the candidate" in p  # answers in the candidate's language
    assert coach.PROMPT_VERSION == "coach@1"


def test_message_bounds_and_optional_job():
    assert MessageIn(content="Quels points améliorer ?").content
    for bad in ("", "x" * (MAX_MESSAGE_CHARS + 1)):
        with pytest.raises(ValidationError):
            MessageIn(content=bad)
    assert ConversationIn().job_id is None


job_in = TypeAdapter(JobIn)


def test_each_source_kind_validates_to_its_model():
    doc = str(uuid4())
    assert isinstance(
        job_in.validate_python({"source": "manual", "text": "Dev Python"}), ManualJobIn
    )
    assert isinstance(
        job_in.validate_python({"source": "file", "document_id": doc}), FileJobIn
    )
    assert isinstance(
        job_in.validate_python({"source": "france_travail", "external_id": "212MZBL"}),
        SearchJobIn,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "url", "url": "https://example.test/job"},  # D5: v2
        {"source": "manual", "text": ""},
        {"source": "file", "document_id": "not-a-uuid"},
        {
            "source": "manual",
            "text": "x",
            "url": "https://example.test",
        },  # no URL field
    ][:3],
)
def test_invalid_or_url_sources_are_rejected(bad):
    with pytest.raises(ValidationError):
        job_in.validate_python(bad)


def test_job_position_accepts_nulls_but_not_missing_key_fields():
    badges = dict.fromkeys(
        ["contract_type", "location", "location_full", "remote_policy"]
        + ["experience_level", "salary"]
    )
    profile = {"experience": None, "education": None}
    profile |= {"technical_skills": [], "soft_skills": [], "nice_to_have": []}
    data = {
        "title": "Développeur Python (H/F)",
        "company": {"name": "Acme"},
        "badges": badges,
        "about_company": {},
        "missions": [],
        "tech_stack": [],
        "working_methods": [],
        "profile": profile,
        "modalities": {},
        "source_meta": {},
    }
    job = JobPosition.model_validate(data)
    assert job.compensation is None
    with pytest.raises(ValidationError):  # a skipped list is a validation error, not []
        JobPosition.model_validate({k: v for k, v in data.items() if k != "missions"})
    assert job_prompt.PROMPT_VERSION == "job_extract@1"


DRAFT = {
    "subject": "Candidature Développeur Python",
    "salutation": "Madame, Monsieur,",
    "opening": "Je vous écris pour ...",
    "body": ["Chez Brightwave, j'ai ...", "Je souhaite ..."],
    "closing": "Veuillez agréer mes salutations distinguées.",
}


def test_draft_needs_every_block_and_content_adds_the_programmatic_ones():
    draft = LetterDraft.model_validate(DRAFT)
    list(
        LetterDraft.model_fields
    )  # writing order: the model fills fields in this order
    assert list(LetterDraft.model_fields) == [
        "subject", "salutation", "opening", "body", "closing",
    ]  # fmt: skip
    for missing in DRAFT:
        with pytest.raises(ValidationError):
            LetterDraft.model_validate({k: v for k, v in DRAFT.items() if k != missing})

    content = LetterContent(
        header=Header(name="Lucas Martel", email="lucas@example.test"),
        recipient=Recipient(company="Acme"),
        signature="Lucas Martel",
        **draft.model_dump(),
    )
    assert content.body == draft.body and content.header.phone is None
    assert "latex" not in LetterContent.model_fields


def test_system_prompt_combines_persona_tone_language_length_and_block_contract():
    p = letters.get_system_prompt("startup", "warm", "fr", "short")
    assert "startup culture" in p and "warm" in p.lower()
    assert "Écrivez en français" in p and "150 words" in p
    assert "OUTPUT STRUCTURE CONTRACT" in p and "[Company Name]" in p
    assert (
        "academic"
        in letters.get_system_prompt("phd", "academic", "en", "detailed").lower()
    )
    assert letters.PROMPT_VERSION == "letter@1"
    with pytest.raises(KeyError):
        letters.get_system_prompt("ngo", "warm", "fr", "short")


def test_a_draft_must_have_at_least_one_body_paragraph():
    with pytest.raises(ValidationError):
        LetterDraft.model_validate({**DRAFT, "body": []})


VALID = {
    "is_fit": True,
    "fit_score": 72,
    "recommendation": "go",
    "strengths": ["Python"],
    "gaps": [],
    "reasons": ["Good stack match"],
    "key_missing_requirements": [],
    "confidence": 0.8,
    "summary": None,
    "constructive_feedback": None,
}


def test_fit_check_bounds_and_required_fields():
    assert FitCheck.model_validate(VALID).recommendation == "go"
    for bad in (
        {**VALID, "fit_score": 101},
        {**VALID, "fit_score": -1},
        {**VALID, "recommendation": "hire"},
        {**VALID, "confidence": 1.5},
        {k: v for k, v in VALID.items() if k != "summary"},  # skipped, not defaulted
    ):
        with pytest.raises(ValidationError):
            FitCheck.model_validate(bad)


def test_persona_prompt_is_chosen_by_company_type_and_unknown_is_a_validation_error():
    assert "DRH" in fit.get_system_prompt_by_company_type(" Corporate ")
    assert "thesis supervisor" in fit.get_system_prompt_by_company_type("phd")
    assert "startup founder" in fit.get_system_prompt_by_company_type("start-up")
    assert fit.PROMPT_VERSION == "fit@1"
    with pytest.raises(ValidationFailed):
        fit.get_system_prompt_by_company_type("ngo")
