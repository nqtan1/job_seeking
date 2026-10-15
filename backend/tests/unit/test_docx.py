"""DOCX -> text at the upload boundary: content, limits, and refusals."""

import io
import zipfile

import pytest

from recruitai.core.errors import ValidationFailed
from recruitai.modules.documents import docx as docx_module
from recruitai.modules.documents.docx import docx_to_text, is_docx

_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _p(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def make_docx(
    body: str, header: str | None = None, document_xml: str | None = None
) -> bytes:
    """A minimal real .docx: one paragraph per line of ``body`` (a table cell for a line
    starting with ``|``), plus an optional header part."""
    paras = "".join(
        f"<w:tbl><w:tr><w:tc>{_p(line[1:])}</w:tc></w:tr></w:tbl>"
        if line.startswith("|")
        else _p(line)
        for line in body.split("\n")
    )
    doc = document_xml or f"<w:document {_NS}><w:body>{paras}</w:body></w:document>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
        if header:
            z.writestr("word/header1.xml", f"<w:hdr {_NS}>{_p(header)}</w:hdr>")
    return buf.getvalue()


def test_body_table_and_header_text_are_read_in_order():
    data = make_docx("Experience\n|Acme 2020-2024", header="jane@example.test")

    assert is_docx(data)
    assert docx_to_text(data) == "Experience\nAcme 2020-2024\njane@example.test"


@pytest.mark.parametrize(
    "data",
    [
        make_docx("x", document_xml='<!DOCTYPE d [<!ENTITY a "aaaa">]><w:document/>'),
        make_docx(""),  # no text at all
        b"PK\x03\x04not really a zip",
    ],
    ids=["dtd", "empty", "broken"],
)
def test_unsafe_empty_or_broken_files_are_refused(data: bytes):
    with pytest.raises(ValidationFailed):
        docx_to_text(data)


def test_an_oversized_part_is_refused_before_it_is_parsed(monkeypatch):
    monkeypatch.setattr(docx_module, "MAX_PART_BYTES", 50)

    with pytest.raises(ValidationFailed):
        docx_to_text(
            make_docx("a long enough paragraph to pass fifty bytes of xml easily")
        )
