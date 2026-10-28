"""One language rule, appended to every prompt that writes text for the user."""

from recruitai.core.language import Language

_NAME: dict[str, str] = {
    "en": "English",
    "fr": "French (français)",
    "vi": "Vietnamese (tiếng Việt)",
}


def with_language(system: str, language: Language) -> str:
    return (
        f"{system}\n\nOUTPUT LANGUAGE (mandatory): write every sentence, label and list item "
        f"you produce in {_NAME[language]} only, whatever the language of the CV, the job or "
        "the user's question. Never mix languages inside a field or an answer. Keep only "
        "proper nouns (people, companies, products, technologies, job titles quoted from the "
        "posting) exactly as written."
    )
