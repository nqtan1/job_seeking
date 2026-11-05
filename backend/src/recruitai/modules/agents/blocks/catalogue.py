"""The catalogue of action blocks (ADR 0032, 0036): the one place that says what each block is.

A block is a row here (what it takes, what it gives back, what it costs, which rules apply) plus one
handler in ``tools.py``. Nothing else in the backend names a block kind: the graph validator, the
engine, the cost estimate and the daily caps all read this table, so adding a block cannot leave one
of them behind. Pure data, no I/O, so ``graph.py`` can import it."""

from dataclasses import dataclass
from typing import NamedTuple


class Cap(NamedTuple):
    """Daily limits of a block with an outside effect. ``once``: a resumed step does not repeat it."""

    user: int  # per user per day
    everyone: int | None = None  # all users together per day
    once: bool = True  # False: repeatable (counted, but a resumed step just runs again)


Ports = tuple[tuple[str, bool], ...]  # (input name, required)


@dataclass(frozen=True)
class Block:
    inputs: Ports
    outputs: tuple[str, ...]
    cap: Cap | None = None  # None: no outside effect worth a ledger row
    ai_uses: int = 0  # model calls one step can make (the daily AI quota)
    needs_job: bool = False  # the run must be given a job
    starts_runs: bool = False  # starts other runs: allowed one level deep only
    pauses: bool = False  # parks the run until it is woken (the engine owns this state)


BLOCKS: dict[str, Block] = {
    "web_search": Block((("query", True),), ("text", "sources"), ai_uses=1),
    "job_search": Block((("query", True), ("department", False)), ("text", "count")),
    # new offers of a search (not yet saved as Jobs), saved with their full text; ``items`` is JSON,
    # one object per offer (job_id, title, company, place, url) for for_each
    "find_offers": Block(
        (("query", True), ("department", False)),
        ("items", "text", "count", "remaining"),
        cap=Cap(30, once=False),  # searches a day: each fetches up to 5 full offers
        ai_uses=1,  # reads the search sentence
    ),
    # the fit analysis of the run's job (the app's tested fit prompts); "start" hangs it off Start
    "fit_check": Block(
        (("start", False), ("employer", False)),
        ("score", "verdict", "strengths", "gaps", "missing", "reasons"),
        ai_uses=1,
        needs_job=True,
    ),
    # starts one run of another automation per item (ADR 0034); the items' keys fill its Start step.
    # Repeatable: a resumed step starts the runs still missing (idempotency keys stop duplicates).
    "for_each": Block(
        (("items", True),),
        ("started", "text"),
        cap=Cap(20, once=False),
        starts_runs=True,
    ),
    "read_page": Block((("url", True),), ("text",), cap=Cap(200, once=False)),
    # reads the run's chosen job; "start" is an optional link so it can hang off the Input step
    "job_lookup": Block(
        (("start", False),),
        ("title", "company", "place", "description", "url"),
        needs_job=True,
    ),
    "add_to_tracker": Block(
        (("company", True), ("title", False), ("url", False), ("notes", False)),
        ("status",),
        cap=Cap(50),
    ),
    "send_email": Block(
        (("to", True), ("subject", True), ("body", True)), ("status",), cap=Cap(20, 500)
    ),
    # a message to the Telegram chat the run's user linked; the text is the only input
    "telegram_send": Block((("text", True),), ("status",), cap=Cap(100, 5000)),
    "wait": Block(
        (("value", True),), ("value",), pauses=True
    ),  # passes its input on, later
}
