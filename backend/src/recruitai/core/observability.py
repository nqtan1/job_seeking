"""Sentry error tracking (ADR 0040). Off when ``SENTRY_DSN`` is empty (dev, tests, CI).

Privacy: ``before_send`` keeps an allowlist (exception type + stack, tags, release, runtime). It
drops request data, user, exception messages, log messages, breadcrumbs and local variables.
"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from recruitai.config import Settings
from recruitai.core.logging import get_context, scrub

_KEEP = ("event_id", "timestamp", "level", "platform", "logger", "transaction", "sdk",
         "release", "environment", "server_name", "fingerprint")  # fmt: skip
_FRAME_KEEP = ("filename", "abs_path", "module", "function", "lineno", "colno", "in_app",
               "context_line", "pre_context", "post_context")  # fmt: skip
_TAGS = ("request_id", "org_id", "task_id")  # never user_id (ADR 0040: no user data)


def before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    out = {k: event[k] for k in _KEEP if k in event}
    tags = {
        k: v for k, v in (event.get("tags") or {}).items() if k in (*_TAGS, "component")
    }
    tags.update({k: v for k, v in get_context().items() if k in _TAGS})
    out["tags"] = tags
    if runtime := (event.get("contexts") or {}).get("runtime"):
        out["contexts"] = {"runtime": runtime}
    if request := event.get(
        "request"
    ):  # method + path only: no query, body, headers, cookies
        out["request"] = {
            "method": request.get("method"),
            "url": scrub(str(request.get("url") or "").split("?")[0]),
        }
    values = []
    for exc in (event.get("exception") or {}).get("values") or []:
        clean = {k: exc[k] for k in ("type", "module", "mechanism") if k in exc}
        if frames := (exc.get("stacktrace") or {}).get("frames"):
            clean["stacktrace"] = {
                "frames": [{k: f[k] for k in _FRAME_KEEP if k in f} for f in frames]
            }
        values.append(clean)
    if values:
        out["exception"] = {"values": values}
    return out


def init_sentry(settings: Settings, component: str) -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.release or None,
        send_default_pii=False,
        include_local_variables=False,
        max_breadcrumbs=0,
        # traces_sample_rate stays unset: no tracing (spans could carry AI prompts), no profiling.
        before_send=before_send,  # type: ignore[arg-type]
        # Error logs become events (the API's unhandled-error log runs inside the request
        # context, so it carries the request id); INFO logs are not kept as breadcrumbs.
        integrations=[LoggingIntegration(level=None)],
    )
    sentry_sdk.set_tag("component", component)
