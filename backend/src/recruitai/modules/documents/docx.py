"""DOCX -> plain text, at the upload boundary only.

A CV or job description in DOCX is converted to text when it is uploaded and the original is
not kept, so every later reader (extraction, export, the self-hosted model) only ever sees
``text/plain``: one parser, at the trust boundary, with hard limits. Standard library only.
"""

import io
import re
import zipfile
from xml.etree import ElementTree

from recruitai.core.errors import ValidationFailed

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_PART_BYTES = 5 * 1024 * 1024  # uncompressed size of one XML part (a zip bomb guard)
MAX_ENTRIES = 200
_HEADERS = re.compile(r"^word/header\d*\.xml$")


def is_docx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
    except zipfile.BadZipFile:
        return False
    return {"[Content_Types].xml", "word/document.xml"} <= names


def _paragraphs(xml: bytes) -> list[str]:
    # DOCX never needs a DTD; refusing it closes entity-expansion attacks outright.
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValidationFailed("The Word file is not valid.")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ValidationFailed("The Word file is not valid.") from exc
    out: list[str] = []
    for p in root.iter(f"{_W}p"):
        parts: list[str] = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
            elif el.tag == f"{_W}tab":
                parts.append("\t")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            out.append(line)
    return out


def docx_to_text(data: bytes) -> str:
    """Body paragraphs (tables included) then headers, where many CVs put their contact
    details. Raises ``ValidationFailed`` for a broken, oversized or empty file."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = {i.filename: i for i in z.infolist()}
            if len(infos) > MAX_ENTRIES:
                raise ValidationFailed("The Word file is not valid.")
            wanted = [
                "word/document.xml",
                *sorted(n for n in infos if _HEADERS.match(n)),
            ]
            lines: list[str] = []
            for name in wanted:
                info = infos.get(name)
                if info is None:
                    continue
                if info.file_size > MAX_PART_BYTES:
                    raise ValidationFailed("The Word file is too large to read.")
                with z.open(info) as f:
                    xml = f.read(MAX_PART_BYTES + 1)
                if len(xml) > MAX_PART_BYTES:
                    raise ValidationFailed("The Word file is too large to read.")
                lines.extend(_paragraphs(xml))
    except zipfile.BadZipFile as exc:
        raise ValidationFailed("The Word file is not valid.") from exc
    text = "\n".join(lines)
    if not text.strip():
        raise ValidationFailed("No text found in the Word file.")
    return text
