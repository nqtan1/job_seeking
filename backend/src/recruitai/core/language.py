"""The three languages a user can pick. One choice drives the UI, every AI answer and every
e-mail, so nothing is ever shown in a mix of languages."""

from typing import Literal

Language = Literal["en", "fr", "vi"]
DEFAULT_LANGUAGE: Language = "en"
