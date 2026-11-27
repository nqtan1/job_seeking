"""The action blocks of flows (ADR 0032, 0036, 0039), registered as tools of ``core.tools``: the web,
messages and core packs (the career tools register from their own modules).

A block is a row here plus one handler in ``tools.py``. Nothing else in the backend names a block
kind: the graph validator, the engine, the cost estimate and the daily caps all read the registry."""

from typing import Any

from recruitai.core.tools import Call, Cap, Tool, register, register_reader
from recruitai.modules.agents.blocks.tools import HANDLERS
from recruitai.modules.agents.connections import service as connections
from recruitai.modules.agents.flows import repository as flow_repo

_ROWS = (
    Tool(
        "web_search",
        "web",
        (("query", True),),
        ("text", "sources"),
        ai_uses=1,
        chat=True,
        untrusted=True,
        mcp=True,
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


async def _last_run(c: Call) -> dict[str, Any] | None:
    """The account's newest run, for the chat's situation line (ADR 0042). None: no runs."""
    rows = await flow_repo.list_org_runs(
        c.db, org_id=c.org_id, status=None, flow_id=None, before_id=None, limit=1
    )
    if not rows:
        return None
    run, name = rows[0]
    return {"name": name, "status": run.status, "finished_at": run.finished_at}


register_reader("last_run", _last_run)


async def _telegram_chat(c: Call) -> dict[str, Any] | None:
    """The chat the user linked (ADR 0036), for the coach's inbox mirror. None: not linked."""
    if c.user_id is None:
        return None
    chat = await connections.active_chat(c.db, org_id=c.org_id, user_id=c.user_id)
    return None if chat is None else {"chat_id": chat}


register_reader("telegram_chat", _telegram_chat)
