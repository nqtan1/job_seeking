"""The agent tools service (ADR 0043): every registry tool flagged ``mcp``, over MCP (stateless JSON
on streamable HTTP, ``/mcp``). Run it with ``uvicorn --factory recruitai.tools_server:create``.

It trusts the caller for the tenant (``_meta``), so only the api and worker service accounts get in:
Cloud Run IAM first, then the Google ID token is checked again here (a misconfigured invoker must not
open every account's data)."""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import anyio
import mcp_types as types
from mcp.server import Server
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from recruitai import packs  # noqa: F401  registers every tool (ADR 0039)
from recruitai.ai.gateway import LLMGateway
from recruitai.config import Settings, get_settings
from recruitai.core import tools as registry
from recruitai.core.errors import AppError
from recruitai.core.tool_calls import META

logger = logging.getLogger(__name__)

LLMFor = Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]]


def schema(tool: registry.Tool) -> types.Tool:
    """Every input and output is text (the registry's contract); the effect is a hint to clients."""
    text = {"type": "string"}
    return types.Tool(
        name=tool.id,
        input_schema={
            "type": "object",
            "properties": {name: text for name, _ in tool.inputs},
            "required": [name for name, required in tool.inputs if required],
        },
        output_schema={
            "type": "object",
            "properties": {name: text for name in tool.outputs},
        },
        annotations=types.ToolAnnotations(
            read_only_hint=tool.effect == "read",
            open_world_hint=tool.untrusted,
        ),
    )


def served(settings: Settings) -> list[registry.Tool]:
    return [
        t
        for t in registry.all().values()
        if t.mcp and (t.flag is None or getattr(settings, t.flag))
    ]


def _error(code: str, exc: AppError | None = None) -> types.CallToolResult:
    """A fixed code; for an AppError also its status and detail (app-written, never exception
    text), so the caller raises the same error it would get in-process."""
    data: dict[str, Any] = {"code": code}
    if exc is not None:
        data |= {"status": int(exc.status_code), "detail": exc.detail}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=code)],
        is_error=True,
        structured_content=data,
    )


def _tenant(meta: Any) -> tuple[UUID, UUID, UUID | None] | None:
    ctx = meta.get(META) if isinstance(meta, dict) else None
    if not isinstance(ctx, dict):
        return None
    try:
        job = ctx.get("job_id")
        return UUID(ctx["org_id"]), UUID(ctx["user_id"]), UUID(job) if job else None
    except (KeyError, TypeError, ValueError):
        return None


def build_server(
    settings: Settings, sessions: async_sessionmaker[AsyncSession], llm_for: LLMFor
) -> Server[Any]:
    async def list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[schema(t) for t in served(settings)])

    async def call_tool(
        _ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        tool = {t.id: t for t in served(settings)}.get(params.name)
        tenant = _tenant(params.meta)
        if tool is None:
            return _error("unknown_tool")
        if tenant is None:
            return _error("no_tenant")
        org_id, user_id, job_id = tenant
        names = {n for n, _ in tool.inputs}
        values = {k: str(v) for k, v in (params.arguments or {}).items() if k in names}
        async with sessions() as db:
            try:
                llm = await llm_for(db, org_id, user_id)
                out = await registry.handler(tool.id)(
                    registry.Call(db, llm, org_id, user_id, job_id, values)
                )
                await db.commit()
            except AppError as exc:
                await db.rollback()
                return _error(exc.code, exc)
            except Exception as exc:  # noqa: BLE001  (a fixed code, never exception text)
                logger.error(
                    "tool failed",
                    extra={"tool": tool.id, "error_type": type(exc).__name__},
                )
                await db.rollback()
                return _error("tool_failed")
        out = {k: str(v) for k, v in out.items()}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(out))],
            structured_content=out,
        )

    return Server("recruitai-tools", on_list_tools=list_tools, on_call_tool=call_tool)


class Callers:
    """Google ID tokens of the allowed service accounts; ``audience`` None = no check (ENV=local)."""

    def __init__(self, audience: str | None, emails: set[str]) -> None:
        self.audience, self.emails = audience, emails
        # ponytail: verified tokens kept until they expire, one dict per process; fine for two callers
        self._ok: dict[str, float] = {}

    async def allowed(self, authorization: str) -> bool:
        if self.audience is None:
            return True
        token = authorization.removeprefix("Bearer ").strip()
        if self._ok.get(token, 0) > time.time():
            return True
        claims = await anyio.to_thread.run_sync(self._verify, token)
        if not claims or not claims.get("email_verified"):
            return False
        if claims.get("email") not in self.emails:
            return False
        self._ok = {t: e for t, e in self._ok.items() if e > time.time()}
        self._ok[token] = float(claims["exp"])
        return True

    def _verify(self, token: str) -> dict[str, Any] | None:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        try:
            claims: dict[str, Any] = id_token.verify_oauth2_token(
                token, GoogleRequest(), audience=self.audience
            )
        except ValueError:  # bad signature, audience or expiry
            return None
        return claims


class Guard:
    """Every path but ``/health`` (Cloud Run's startup probe) needs an allowed caller."""

    def __init__(self, app: ASGIApp, callers: Callers) -> None:
        self.app, self.callers = app, callers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] != "/health":
            auth = Request(scope).headers.get("authorization", "")
            if not await self.callers.allowed(auth):
                response: Response = JSONResponse({"code": "forbidden"}, 403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(
    settings: Settings, sessions: async_sessionmaker[AsyncSession], llm_for: LLMFor
) -> Starlette:
    if settings.env != "local" and not settings.tools_audience:
        raise RuntimeError("TOOLS_AUDIENCE is required outside ENV=local")

    async def health(_request: Request) -> Response:
        return PlainTextResponse("ok")

    app = build_server(settings, sessions, llm_for).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # behind Cloud Run (any Host); callers are checked by `guarded`
        custom_starlette_routes=[Route("/health", health)],
    )
    emails = {e.strip() for e in settings.tools_callers.split(",") if e.strip()}
    app.add_middleware(Guard, callers=Callers(settings.tools_audience, emails))
    return app


def create() -> Starlette:
    """The uvicorn factory: the real database and the tenant-bound LLM gateway."""
    from recruitai.ai.dependencies import build_llm_gateway
    from recruitai.ai.overrides import effective_settings
    from recruitai.core.db import create_engine, create_session_factory
    from recruitai.core.logging import configure_logging
    from recruitai.core.observability import init_sentry

    settings = get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings, "tools")
    sessions = create_session_factory(
        create_engine(settings, application_name="recruitai-tools")
    )

    async def llm_for(db: AsyncSession, org_id: UUID, user_id: UUID) -> LLMGateway:
        effective = await effective_settings(settings, db)
        return build_llm_gateway(effective, db, org_id=org_id, user_id=user_id)

    return create_app(settings, sessions, llm_for)
