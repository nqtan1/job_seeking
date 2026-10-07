"""``letters:render_pdf``: letter → LaTeX → Tectonic → PDF → storage (ADR 0010).

Runs in the worker only. Layers of defence for the LaTeX we compile (raw mode accepts text a
user wrote): (1) ``check_tex_allowed`` rejects dangerous commands before compiling, with a
clean error; (2) Tectonic runs with ``--untrusted`` (no shell escape, no external files), a
wall-clock timeout and a memory limit; (3) templated letters are escaped, so they can't form
a command at all (``latex_escape``).

Failures set ``render_status='failed'`` and a *safe* ``error_code`` on the ``task_runs`` row
(never exception text). Transient failures (a compiler crash, a timeout) are retried 3 times;
an input the user must fix (forbidden command) fails at once.
"""

import asyncio
import logging
import re
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import procrastinate
from procrastinate import JobContext
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import ValidationFailed
from recruitai.core.storage import Storage
from recruitai.core.tasks import mark_done, mark_failed
from recruitai.modules.documents import service as documents
from recruitai.modules.letters import repository
from recruitai.modules.letters.schemas import LetterContent
from recruitai.modules.letters.templates import render_tex

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
COMPILE_TIMEOUT_S = 60.0
COMPILE_MEMORY_BYTES = 2 * 1024**3

# A LaTeX control word ends at the first non-letter, so `\write18` must match `\write`.
_FORBIDDEN = re.compile(
    r"\\(?:write|immediate|openin|openout|newwrite|newread|read|readline|input|include|"
    r"InputIfFileExists|IfFileExists|verbatiminput|lstinputlisting|catcode|special|"
    r"csname|directlua)(?![A-Za-z])"
    r"|\^\^",  # `^^5c` spells a backslash: a way to hide any of the above
)


class RenderError(Exception):
    """Carries a safe, stable ``code`` for ``task_runs.error_code``. ``retryable`` says whether
    running again could help."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def check_tex_allowed(tex: str) -> None:
    if _FORBIDDEN.search(tex):
        raise RenderError("render_forbidden_input", retryable=False)


async def compile_tex(
    tex: str, *, timeout_s: float = COMPILE_TIMEOUT_S, binary: str = "tectonic"
) -> bytes:
    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / "letter.tex"
        source.write_text(tex, encoding="utf-8")
        # The memory cap is set by a tiny `sh` wrapper (`ulimit -v`, in KiB) that then execs the
        # compiler: no `preexec_fn`, which is unsafe in a process that also runs threads.
        proc = await asyncio.create_subprocess_exec(
            "sh", "-c", 'ulimit -v "$0" && exec "$@"', str(COMPILE_MEMORY_BYTES // 1024),
            binary, "-X", "compile", "--untrusted", "--outdir", workdir, str(source),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=workdir,
        )  # fmt: skip
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RenderError("render_timeout", retryable=True) from None
        if (
            proc.returncode == 127
        ):  # `exec` could not find the compiler: a retry will not help
            raise RenderError("render_unavailable", retryable=False)
        pdf = Path(workdir) / "letter.pdf"
        if proc.returncode != 0 or not pdf.exists():
            raise RenderError("render_failed", retryable=True)
        return pdf.read_bytes()


async def render_letter(
    session: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    letter_id: UUID,
    compile_pdf: Callable[[str], Awaitable[bytes]] = compile_tex,
) -> UUID:
    """Render one letter and point it at its new PDF document. Returns the document id.
    The caller commits (or marks the failure)."""
    letter = await repository.get(
        session, org_id=org_id, letter_id=letter_id, for_update=True
    )
    if letter is None:
        raise RenderError("letter_not_found", retryable=False)
    tex = letter.latex_override or render_tex(
        LetterContent.model_validate(letter.content),
        template=letter.template,  # type: ignore[arg-type]  # DB CHECK limits the values
        language=letter.language,  # type: ignore[arg-type]
    )
    check_tex_allowed(tex)
    content_at_start, override_at_start = letter.content, letter.latex_override
    # Release the row lock while the (slow) compiler runs; re-take it to record the result.
    await session.commit()
    pdf = await compile_pdf(tex)
    try:
        document = await documents.store_generated(
            session, storage, org_id=org_id, kind="letter_pdf", data=pdf
        )
    except ValidationFailed as exc:  # the compiler produced something that isn't a PDF
        raise RenderError("render_failed", retryable=True) from exc
    letter = await repository.get(
        session, org_id=org_id, letter_id=letter_id, for_update=True
    )
    if letter is None:
        raise RenderError("letter_not_found", retryable=False)
    if letter.content != content_at_start or letter.latex_override != override_at_start:
        # Edited while compiling: this PDF shows the old text. Discard it rather than present
        # it as the letter's PDF; the user renders again.
        await documents.delete_document(
            session, storage, org_id=org_id, document_id=document.id
        )
        await session.commit()
        raise RenderError("letter_changed", retryable=False)
    previous = letter.pdf_document_id
    letter.pdf_document_id = document.id
    letter.render_status = "done"
    await session.flush()
    if previous is not None:  # the old PDF is replaced, not orphaned
        await documents.delete_document(
            session, storage, org_id=org_id, document_id=previous
        )
    return document.id


async def mark_render_failed(
    session: AsyncSession, *, org_id: UUID, letter_id: UUID
) -> None:
    letter = await repository.get(
        session, org_id=org_id, letter_id=letter_id, for_update=True
    )
    if letter is not None and letter.render_status == "queued":
        # Only a render that is still pending can fail: an edit meanwhile already reset it.
        letter.render_status = "failed"
        await session.flush()


blueprint = procrastinate.Blueprint()


@blueprint.task(
    name="render_pdf",
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=MAX_ATTEMPTS, exponential_wait=5),
)
async def render_pdf(
    context: JobContext, task_run_id: str, org_id: str, letter_id: str
) -> None:
    from recruitai.worker import (  # the worker owns the resources
        session_factory,
        storage,
    )

    run_id, org, letter = UUID(task_run_id), UUID(org_id), UUID(letter_id)
    async with session_factory() as session:
        try:
            document_id = await render_letter(
                session, storage, org_id=org, letter_id=letter, compile_pdf=compile_tex
            )
            await session.commit()
            await mark_done(session, run_id, result_ref=str(document_id))
            return
        except RenderError as exc:
            await session.rollback()
            code, retryable = exc.code, exc.retryable
        except Exception as exc:  # noqa: BLE001  (unexpected: becomes a safe code below)
            await session.rollback()
            # The type only: the message could contain letter text (never logged).
            logger.error(
                "render_pdf failed",
                extra={"error_type": type(exc).__name__, "task_run_id": task_run_id},
            )
            code, retryable = "render_failed", True
        last_attempt = context.job.attempts + 1 >= MAX_ATTEMPTS
        if retryable and not last_attempt:
            raise RuntimeError(code)  # Procrastinate retries with backoff
        await mark_render_failed(session, org_id=org, letter_id=letter)
        await session.commit()
        await mark_failed(session, run_id, error_code=code)
