"""Runs a tool where it lives (ADR 0043): on the tools service over MCP when ``TOOLS_URL`` is set,
in-process otherwise. Chat, confirmed actions, flow steps and the Tools page all come through here,
so a tool behaves the same whoever calls it. Caps, quotas and proposals stay with the caller."""

import logging
import re
import time
from typing import Any, cast

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import RequestParamsMeta
from mcp_types.version import LATEST_MODERN_VERSION

from recruitai.config import get_settings
from recruitai.core.tools import Call, Tool, ToolFailed, handler

logger = logging.getLogger(__name__)

META = "recruitai/context"  # the tenant of a call travels here, never in the model's arguments
_CODE = re.compile(r"[a-z][a-z0-9_]*")  # AppError codes are snake_case
_TOKEN_TTL_S = 45 * 60  # Google ID tokens live 1 h
_tokens: dict[str, tuple[str, float]] = {}  # audience -> (token, fetched at)


class ToolsUnavailable(ToolFailed):
    code = "tools_unavailable"
    default_detail = "The tools service did not answer. Try again in a minute."


def remote(tool: Tool) -> bool:
    return tool.mcp and bool(get_settings().tools_url)


async def invoke(tool: Tool, call: Call) -> dict[str, str]:
    url = get_settings().tools_url
    if not (tool.mcp and url):
        return await handler(tool.id)(call)
    # nothing held open across the network; the tool commits its own writes
    await call.db.commit()
    # an open map (extra keys allowed), which mypy cannot express yet (PEP 728)
    meta = cast(
        RequestParamsMeta,
        {
            META: {
                "org_id": str(call.org_id),
                "user_id": str(call.user_id) if call.user_id else None,
                "job_id": str(call.job_id) if call.job_id else None,
            }
        },
    )
    # derived, not guessed: each AI use may take a full model call
    timeout = get_settings().ai_call_timeout_s * (tool.ai_uses + 1) + 10
    try:
        async with await _client(url, timeout) as client:
            result = await client.call_tool(tool.id, call.values, meta=meta)
    except Exception as exc:  # noqa: BLE001  (a fixed code, never exception text)
        logger.warning(
            "tools service call failed",
            extra={"tool": tool.id, "error_type": type(exc).__name__},
        )
        raise ToolsUnavailable() from None
    data: dict[str, Any] = result.structured_content or {}
    if result.is_error:
        raise _error(data)
    return {k: str(v) for k, v in data.items()}


def _error(data: dict[str, Any]) -> ToolFailed:
    """The service's AppError again, same code, status and (app-written) detail, so a call
    behaves the same in-process and remote (a 404 stays a 404)."""
    code = str(data.get("code") or "")
    detail = str(data.get("detail") or "")[:300] or None
    err = ToolFailed(detail, code=code if _CODE.fullmatch(code) else "tool_failed")
    status = data.get("status")
    if isinstance(status, int) and 400 <= status < 500:
        err.status_code = status
    return err


async def status() -> dict[str, Any]:
    """The Tools page's health check, on demand only (an idle service must stay at zero)."""
    url = get_settings().tools_url
    if not url:
        return {"remote": False, "ok": True, "served": None, "latency_ms": 0}
    began = time.monotonic()
    try:
        async with await _client(url, 15) as client:
            listed = await client.list_tools()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tools service check failed", extra={"error_type": type(exc).__name__}
        )
        return {"remote": True, "ok": False, "served": [], "latency_ms": 0}
    return {
        "remote": True,
        "ok": True,
        "served": sorted(t.name for t in listed.tools),
        "latency_ms": int((time.monotonic() - began) * 1000),
    }


async def _client(url: str, timeout: float) -> Client:
    headers = {}
    if url.startswith("https://"):  # Cloud Run: an ID token of this service's account
        headers["Authorization"] = f"Bearer {await _token(url.removesuffix('/mcp'))}"
    http = http_client(headers, timeout)
    # pinned to the modern protocol: one request per call, no discovery round trip
    return Client(
        streamable_http_client(url, http_client=http), mode=LATEST_MODERN_VERSION
    )


def http_client(headers: dict[str, str], timeout: float) -> httpx2.AsyncClient:
    """Tests replace this to reach the server in-process."""
    return httpx2.AsyncClient(headers=headers, timeout=timeout)


async def _token(audience: str) -> str:
    kept = _tokens.get(audience)
    if kept and time.monotonic() - kept[1] < _TOKEN_TTL_S:
        return kept[0]
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    token: str = await anyio.to_thread.run_sync(
        lambda: id_token.fetch_id_token(Request(), audience)
    )
    _tokens[audience] = (token, time.monotonic())
    return token
