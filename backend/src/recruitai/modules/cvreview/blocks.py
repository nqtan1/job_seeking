"""Deterministic CV text -> blocks (the anchor for comments and live edits). Pure, no I/O."""

import io
import logging
import re
import unicodedata

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from recruitai.modules.cvreview.schemas import MAX_BLOCKS, MAX_CHARS, Block

logging.getLogger("pypdf").setLevel(
    logging.ERROR
)  # its warnings can quote raw PDF bytes (CV text)

MAX_PAGES = (
    10  # a CV longer than this is not read further (parse cost on the event loop)
)

_SECTIONS = {  # heading synonyms (en + fr + vi), "|"-separated
    "summary": "summary|profile|about me|about|objective|professional summary|résumé|profil|à propos|"
    "giới thiệu|giới thiệu bản thân|mục tiêu|mục tiêu nghề nghiệp|tóm tắt",
    "experience": "experience|work experience|professional experience|employment|work history|"
    "expérience|expérience professionnelle|expériences professionnelles|parcours professionnel|"
    "kinh nghiệm|kinh nghiệm làm việc|quá trình làm việc",
    "projects": "projects|personal projects|side projects|selected projects|projets|projets personnels|"
    "dự án|dự án cá nhân",
    "skills": "skills|technical skills|tech stack|technologies|core skills|compétences|compétences techniques|"
    "kỹ năng|kĩ năng|kỹ năng chuyên môn",
    "education": "education|education and training|education and certifications|studies|formation|formations|"
    "éducation|études|diplômes|học vấn|trình độ học vấn",
    "other": "certifications|certificates|languages|interests|hobbies|awards|publications|volunteering|"
    "langues|centres d intérêt|certifications et formations|chứng chỉ|ngôn ngữ|sở thích|giải thưởng",
}
_NON_WORD = re.compile(r"[\W_]+")


def _key(s: str) -> str:
    """Heading lookup key: NFC, lowercase, '&' as 'and', ornaments/punctuation/colon dropped."""
    s = unicodedata.normalize("NFC", s).lower().replace("&", " and ")
    return _NON_WORD.sub(" ", s).strip()


_HEADINGS = {_key(h): s for s, hs in _SECTIONS.items() for h in hs.split("|")}
_BULLET = re.compile(r"^\s*[-*•–●▪◦■➢➤·\uf0b7]\s*")


def extract_text(data: bytes, mime: str) -> tuple[str, int] | None:
    """(text, pages) from the PDF text layer or utf-8 text (documents stores DOCX already as
    text). None if empty/unreadable. Reads at most MAX_PAGES pages."""
    pages = 1
    try:
        if mime == "application/pdf":
            reader = PdfReader(io.BytesIO(data))
            pages = min(len(reader.pages), MAX_PAGES)
            text = "\n".join(p.extract_text() or "" for p in reader.pages[:MAX_PAGES])
        elif mime.startswith("text/"):
            text = data.decode("utf-8", errors="replace")
        else:
            return None
    except (
        PyPdfError,
        ValueError,
        OSError,
    ):  # unreadable PDF: same outcome as "no text"
        return None
    text = text.replace("\x00", "").strip()  # NUL cannot be stored in JSONB
    return (text, pages) if text else None


def split_blocks(text: str) -> tuple[list[Block], bool]:
    """(blocks, truncated): truncated when the CV had more than MAX_BLOCKS lines."""
    out: list[dict[str, str]] = []
    section, blank = "header", True
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            blank = True
            continue
        last = out[-1] if out else None
        if len(line) <= 40 and (sec := _HEADINGS.get(_key(line))):
            section = sec
            out.append(
                {"kind": "heading", "section": section, "text": line.rstrip(":")}
            )
        elif _BULLET.match(raw):
            if body := _BULLET.sub("", raw).strip():  # a lone glyph is nothing
                out.append({"kind": "bullet", "section": section, "text": body})
        elif (
            last
            and last["kind"] == "bullet"
            and not blank
            and (line[0].islower() or last["text"][-1] in ",-(/")
        ):
            last["text"] += f" {line}"  # wrapped line: join into the previous bullet
        else:
            out.append({"kind": "text", "section": section, "text": line})
        blank = False
    if not any(
        b["kind"] == "heading" for b in out
    ):  # no headings: still review everything
        for b in out[3:]:  # ponytail: the first 3 lines are the header
            b["section"] = "experience"
    blocks = [
        Block.model_validate({"id": f"b{i}", **b, "text": b["text"][:MAX_CHARS]})
        for i, b in enumerate(out[:MAX_BLOCKS], 1)
    ]
    return blocks, len(out) > MAX_BLOCKS
