"""Plain-text and email-body versions of a letter, derived from the structured blocks (§10.2).
No model call and no LaTeX: just the blocks, in reading order. DOCX, LinkedIn-message and
follow-up-email formats are v2."""

from recruitai.modules.letters.schemas import LetterContent


def _paragraphs(c: LetterContent) -> list[str]:
    return [c.salutation, c.opening, *c.body, c.closing]


def to_text(c: LetterContent) -> str:
    """For web forms that take a text box: the letter only, no address blocks or date."""
    return "\n\n".join([*_paragraphs(c), c.signature]).strip()


def to_email(c: LetterContent) -> tuple[str, str]:
    """``(subject, body)`` for an application email: the letter, then the sender's contacts
    under the signature so the recruiter can reply."""
    contacts = [v for v in (c.header.email, c.header.phone) if v]
    signature = "\n".join([c.signature, *contacts])
    return c.subject, "\n\n".join([*_paragraphs(c), signature]).strip()
