# 0003 · Keep Python + FastAPI for the backend

- **Status:** Accepted

## Context
The backend is already FastAPI + Pydantic. The core of the product is LLM
calls plus document parsing (PDF text extraction, LaTeX). The developer's
strongest language is Python.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Python + FastAPI** ✅ | Existing code and knowledge; Pydantic gives validation, OpenAPI and LLM structured-output schemas from one model; best AI and document ecosystem (google-genai, pdfplumber, Jinja) | Slower than Go/Node for CPU-bound work (not our bottleneck: we wait on Gemini). Async and sync mixing needs care |
| **Django + DRF** | Built-in admin, ORM, auth, migrations | Heavier; its async support is weaker; we'd rewrite everything; its admin and auth overlap with Firebase |
| **Node.js (NestJS / Hono)** | One language on front and back | Rewrite of all domain code; weaker PDF/document tooling; Pydantic ↔ LLM schema synergy lost |
| **Go** | Performance, single binary | Much slower to develop business logic; weak LLM/document ecosystem; full rewrite |

## Decision
Keep Python 3.13 + FastAPI. Tooling:
- `uv` for dependencies
- `ruff` for lint and format
- `mypy --strict` on `src/`
- `pytest` for tests

## Why
The bottleneck is LLM latency (seconds), not framework overhead
(microseconds). Pydantic models are the **single source of truth** for three
things: API validation, the OpenAPI schema (and so frontend types), and
Gemini's `response_schema`. No other stack gives us that for free.

## Consequences
- **Good:** no rewrite of domain code; strong typing with mypy + Pydantic.
- **Bad:** blocking libraries (pdfplumber, some SDK calls) must run in
  threads (`run_in_threadpool` / `anyio.to_thread`), or they block the event
  loop. This is enforced in review.
- **Follow-ups:** a pre-commit config; a mypy baseline on the new code only.

## When to reconsider
Practically never for this product. Only for a CPU-heavy feature (for
example, local ML inference), which would then be a separate service anyway.
