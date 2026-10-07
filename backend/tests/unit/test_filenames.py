"""core/filenames.py: readable, header-safe download names."""

from recruitai.core.filenames import content_disposition, safe_filename


def test_names_are_readable_safe_and_keep_accents():
    assert (
        safe_filename(
            "Motivation letter", "Éloïse N'Guyen", None, "Acme/Corp", ext="pdf"
        )
        == "Motivation letter - Éloïse N'Guyen - Acme Corp.pdf"
    )
    assert safe_filename('a"b\r\nc', "../x", ext="pdf") == "a b c - .. x.pdf"
    assert safe_filename(None, ext="pdf") == "Document.pdf"
    assert len(safe_filename("x" * 500, ext="pdf")) <= 104


def test_disposition_has_ascii_fallback_and_utf8_name():
    header = content_disposition("Lettre - Éloïse.pdf", attachment=True)
    assert header.startswith('attachment; filename="Lettre - lose.pdf"')
    assert "filename*=UTF-8''Lettre%20-%20%C3%89lo%C3%AFse.pdf" in header
    assert content_disposition("a.pdf", attachment=False).startswith("inline;")
