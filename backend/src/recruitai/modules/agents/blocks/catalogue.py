"""The action blocks of flows (ADR 0032, 0036, 0039), registered as tools of ``core.tools``: the web,
messages and core packs (the career tools register from their own modules).

A block is a row here plus one handler in ``tools.py``. Nothing else in the backend names a block
kind: the graph validator, the engine, the cost estimate and the daily caps all read the registry."""

from recruitai.core.tools import Cap, Tool, register
from recruitai.modules.agents.blocks.tools import HANDLERS

_ROWS = (
    Tool(
        "web_search",
        "web",
        (("query", True),),
        ("text", "sources"),
        ai_uses=1,
        chat=True,
        untrusted=True,
    ),
    # starts one run of another automation per item (ADR 0034); the items' keys fill its Start step.
    # Repeatable: a resumed step starts the runs still missing (idempotency keys stop duplicates).
    Tool(
        "for_each",
        "core",
        (("items", True),),
        ("started", "text"),
        cap=Cap(20, once=False),
        starts_runs=True,
    ),
    Tool(
        "read_page",
        "web",
        (("url", True),),
        ("text",),
        cap=Cap(200, once=False),
        untrusted=True,
    ),
    Tool(
        "send_email",
        "messages",
        (("to", True), ("subject", True), ("body", True)),
        ("status",),
        effect="outside",
        cap=Cap(20, 500),
    ),
    # a message to the Telegram chat the run's user linked; the text is the only input
    Tool(
        "telegram_send",
        "messages",
        (("text", True),),
        ("status",),
        effect="outside",
        cap=Cap(100, 5000),
    ),
    # passes its input on, later
    Tool("wait", "core", (("value", True),), ("value",), pauses=True),
)
for _t in _ROWS:
    register(_t, HANDLERS.get(_t.id))
