# 0012 · Typed API client generated from OpenAPI

- **Status:** Accepted

## Context
Today `frontend/api.js` rewrites every endpoint and payload by hand. A
backend rename breaks the UI at runtime, for users.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Hand-written client** (current) | No tooling | Drift, runtime errors |
| **GraphQL** | Flexible queries | A new server layer, schema, and caching complexity; overkill for one client |
| **tRPC** | End-to-end types | TypeScript-only backend; not possible with FastAPI |
| **OpenAPI → TypeScript types (`openapi-typescript` + `openapi-fetch`)** ✅ | FastAPI already produces OpenAPI from our Pydantic models; zero runtime overhead; compile errors on drift | Requires a regeneration step; the quality of the types depends on good response models |

## Decision
`pnpm gen:api` generates `src/lib/api/schema.d.ts` from the backend's
`/openapi.json`. All calls go through the typed `openapi-fetch` client. CI
regenerates the file and fails if it differs from the committed one.

## Why
The backend is already the source of truth (Pydantic). Code generation turns
that into compile-time safety on the frontend for free.

## Consequences
- **Good:** renaming a field breaks the frontend build, not production.
- **Bad:** every route must declare `response_model` and precise types.
  That's good discipline anyway.

## When to reconsider
A second consumer (mobile app, public API): publish the same OpenAPI with
versioning. The decision stays.
