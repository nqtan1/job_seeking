"""letters/export.py (P2-21a): text and email from the same blocks."""

from recruitai.modules.letters.export import to_email, to_text
from tests.unit.test_letters_latex import _content


def test_text_is_the_letter_in_reading_order_without_address_blocks():
    text = to_text(_content())
    assert text.startswith("Madame, Monsieur,\n\nJe vous écris pour ...")
    assert text.endswith("Veuillez agréer mes salutations distinguées.\n\nLucas Martel")
    assert (
        "Chez Brightwave" in text and "Je maîtrise Python & SQL." in text
    )  # not LaTeX-escaped
    assert "12 rue de la Paix" not in text and "2026-10-02" not in text


def test_email_has_a_subject_and_the_senders_contacts_under_the_signature():
    subject, body = to_email(_content())
    assert subject == "Candidature Développeur Python (H/F)"
    assert body.endswith("Lucas Martel\nlucas@example.test\n0102030405")
    assert body.startswith("Madame, Monsieur,")
