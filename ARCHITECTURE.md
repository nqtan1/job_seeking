# RecruitAI: Target Architecture

**Status:** Proposal, v1 · **Scope:** full system redesign done before any more feature work

This document looks at the current codebase, lists the problems that block it
from being production-grade, and defines the target architecture and stack.
Every later code change should follow it. If a decision here turns out wrong,
change this document first, then the code.

---

## 1. Decisions at a glance

| Concern | Today | Target | Why |
|---|---|---|---|
| Backend framework | FastAPI | **FastAPI** (kept) | Good fit already: async, Pydantic-native, generates OpenAPI |
| Backend structure | Layered by type (`api/`, `application/`, `domain/`, `infrastructure/`) spread across 60+ tiny folders | **Modular monolith, one folder per feature** (`modules/<feature>/`) | A feature's code lives in one place and is easy to find |
| Language / tooling | Python 3.13, uv, no linter | Python 3.13, **uv + ruff + mypy + pytest**, pre-commit | Consistent code, catches bugs before CI |
| Config | `os.getenv` scattered across modules, `load_dotenv()` at import time, gitignored YAML | **pydantic-settings**: one typed `Settings` object | One place, validated at startup |
| Database | SQLite files on local disk plus a hand-written migration runner | **PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic** | Multi-instance safe, FKs, JSONB, real migrations |
| Background jobs | Polling thread + `ThreadPoolExecutor` inside the API process | **Procrastinate** (Postgres-backed queue) running as a **separate worker process** | Durable, retries, no extra infrastructure (reuses Postgres) |
| File storage | Local `db/` folders plus `/tmp` | **Object storage** (GCS in prod, local filesystem in dev) behind a `Storage` interface | Stateless containers; files survive restarts |
| Auth / tenancy | Tenant API keys in an env JSON; the key can also be passed in the query string | **Firebase Auth (Identity Platform)** for users, with **organizations + memberships + roles** in Postgres | Real users; the tenant comes from the token, never from the client |
| LLM access | LangChain wrappers around Gemini, with stateful agent objects | **`google-genai` SDK** behind a small **`LLMGateway`** interface; stateless calls with structured output | Fewer dependencies, native JSON schema output, cost tracking |
| PDF (letters) | `latexmk` via subprocess (TeX is not installed in the image, so it fails in Docker) | **Tectonic** (single-binary LaTeX engine) in the worker image | Keeps the LaTeX editing feature and actually works in a container |
| Frontend | Vanilla JS + Tailwind CDN, 1,300-line `index.html`, JS served by a catch-all route | **React + TypeScript + Vite**, TanStack Query, React Router, Tailwind (built), shadcn/ui | Components, types, a real build |
| API contract | Hand-written `fetch` calls | **Typed client generated from OpenAPI** (`openapi-typescript` + `openapi-fetch`) | The frontend breaks at compile time, not at runtime |
| Deploy | One container, service-account key file mounted | **Cloud Run** (api + worker), **Cloud SQL**, **GCS**, **Firebase Hosting**, **Secret Manager** | GCP-native (you already use Vertex AI); no key files |
| CI/CD | None | **GitHub Actions**: lint → typecheck → test → build → deploy | Nothing reaches `main` without passing checks |

---

## 2. Current state: problems found

These are the reasons for the redesign, with evidence from the code.

### 2.1 Architecture
1. **God object.** `backend/workers/background.py` (883 lines) is the job queue *and*
   the repository for candidates, jobs, fit analyses, and applications. Every
   feature depends on it.
2. **Duplicated, diverging code.** `infrastructure/jobs/providers/` and
   `infrastructure/jobs/search/providers/` are two copies of the same provider
   code that have drifted apart. `_sanitize_filename` and the upload-directory
   setup are copy-pasted into `api/cv.py`, `api/applications.py`, and
   `application/fit/service.py`.
3. **Business logic in routers.** `api/cv.py` (442 lines) and
   `api/applications.py` (333 lines) handle file I/O, persistence, and
   orchestration directly.
4. **Wildcard re-export shims.** `infrastructure/jobs/agent.py`, `prompt.py`,
   and `domain/jobs/schema.py` exist only to `import *` from other modules.
5. **Fake singletons.** The pattern `agent = None` / `global agent` in the
   routers never assigns the global, so a new agent is built on every request
   anyway. It's there as a test hook, but it misleads readers.

### 2.2 Data and state
6. **SQLite on local disk.** On Cloud Run each instance gets its own disk, and
   the disk is lost on restart. Two instances means two separate databases.
7. **State is scattered.** Some results go in SQLite, some are JSON files under
   `db/`, and fit results are written to `tempfile.gettempdir()` (lost on
   restart). The job-search cache is a *second* SQLite database.
8. **Schema.** No foreign keys, no indexes on `tenant_id`, timestamps stored as
   TEXT, JSON stored as TEXT. The migration runner is hand-written.

### 2.3 Security
9. **Weak tenancy.** Tenants authenticate with shared API keys from an env var.
   There are no users. The frontend defaults to `default-tenant`.
10. **Secrets in logs.** `get_tenant_context` accepts `api_key` as a **query
    parameter**, and the request middleware logs `str(request.url)`, so API
    keys end up in the logs.
11. **Service-account key file** is mounted into the container
    (`docker-compose.yaml`). The container runs as root.

### 2.4 Runtime and operations
12. **Queue inside the web process.** A polling thread plus a thread pool
    inside the API process competes with request handling. Its metrics are
    in-memory counters that reset on restart and are wrong with more than one
    instance.
13. **PDF generation cannot work in Docker.** `latexmk` is called by
    subprocess, but TeX is not installed in the image. The failure is logged
    and `None` is returned.
14. **Wrong dependencies** (`backend/pyproject.toml`):
    - `genai` is an unrelated PyPI package, not Google's `google-genai`.
    - `vertexai` is deprecated.
    - `dotenv` is not `python-dotenv`.
    - `path` is unused.
    - `pytest` is in runtime dependencies.
    - `pyyaml` is imported optionally but never declared.
15. **Config** relies on `config/agent_config.yaml`, which is gitignored, so a
    fresh clone behaves differently from the author's machine.

### 2.5 Frontend
16. One 1,300-line `index.html` plus about 3,000 lines of untyped JS modules.
    Tailwind comes from the CDN (the Tailwind docs say not to use it in
    production). JS is served by a FastAPI catch-all route (`/{filename}.js`).
    The API contract is duplicated by hand in `api.js`.

### 2.6 What is worth keeping
- **The prompts** (`infrastructure/*/prompt.py`). These are the product's core
  IP. Move them, don't rewrite them.
- **The Pydantic schemas** in `domain/*/schema.py`: CV, job, fit, HR, and
  letter models. They become the LLM output schemas.
- **The France Travail provider** logic (use the newer `search/providers` copy).
- **Structured JSON logging** with request/tenant correlation IDs.
- **The tests' intent**, especially `test_cross_tenant_isolation.py`. They get
  rewritten against the new structure.
- The UX flows: candidate wizard, recruiter hub, application tracker, letter
  co-writing preview.

---

## 3. Target system overview

```mermaid
flowchart LR
    U[Browser<br/>React SPA] -->|HTTPS| H[Firebase Hosting<br/>static SPA + /api rewrite]
    U -->|sign-in| FA[Firebase Auth]
    H -->|/api/*| API[Cloud Run: api<br/>FastAPI]
    API -->|verify ID token| FA
    API --> PG[(Cloud SQL<br/>PostgreSQL 16)]
    API --> GCS[(GCS bucket<br/>uploads & PDFs)]
    API -->|enqueue task| PG
    W[Cloud Run: worker<br/>Procrastinate] -->|poll tasks| PG
    W --> GCS
    W --> LLM[Gemini via<br/>google-genai / Vertex AI]
    API --> LLM
    W --> FT[France Travail API]
    API -. logs/traces .-> OBS[Cloud Logging<br/>+ Error Reporting]
    W -. logs .-> OBS
```

**Principles**
1. **Stateless processes.** All state lives in Postgres or GCS, so any instance
   can serve any request.
2. **Tenant from the token, never from input.** `org_id` is resolved from the
   authenticated user and the active membership. Clients cannot choose it.
3. **Long work goes async.** Anything that can take more than about 10 s, or
   fans out (batch screening, PDF compile, job search with an LLM), becomes a
   task. The API returns `202` with a task id. Single-document extraction may
   stay synchronous.
4. **One module per feature.** Modules talk to each other only through their
   `service.py`, never through another module's repository or tables.
5. **The LLM is a dependency, not the architecture.** Business code calls
   `LLMGateway.generate(schema=..., prompt=...)`. Swapping models or providers
   is a one-file change.

---

## 4. Backend

### 4.1 Layout

```
backend/
├── pyproject.toml            # uv; ruff + mypy + pytest config
├── alembic.ini
├── alembic/                  # migrations
├── src/recruitai/
│   ├── main.py               # create_app(): routers, middleware, exception handlers
│   ├── worker.py             # Procrastinate app entrypoint
│   ├── config.py             # Settings (pydantic-settings)
│   ├── core/
│   │   ├── db.py             # async engine, session dependency, Base
│   │   ├── auth.py           # Firebase token verification → CurrentUser
│   │   ├── tenancy.py        # OrgContext dependency, role checks
│   │   ├── storage.py        # Storage protocol + GCS / local implementations
│   │   ├── errors.py         # AppError hierarchy → RFC 9457 problem+json
│   │   ├── logging.py        # JSON logs, request_id / org_id context
│   │   └── tasks.py          # Procrastinate app + task-status helpers
│   ├── ai/
│   │   ├── gateway.py        # LLMGateway protocol: generate(schema, messages) -> model
│   │   ├── gemini.py         # google-genai implementation (API key or Vertex)
│   │   ├── usage.py          # records tokens/latency/cost per org & feature
│   │   └── prompts/          # versioned prompt modules (moved from infrastructure/*)
│   └── modules/
│       ├── identity/         # users, organizations, memberships, invites
│       ├── documents/        # upload, type/size validation, text extraction (pdfplumber)
│       ├── candidates/       # CV → CandidateProfile extraction & CRUD
│       ├── jobs/             # job postings: manual/file extraction + external search
│       │   └── providers/    # JobProvider protocol, france_travail.py
│       ├── matching/         # fit analysis (candidate side) & batch screening (recruiter side)
│       ├── letters/          # letter generation, drafts, LaTeX → PDF (Tectonic)
│       └── applications/     # application tracker + status history
└── tests/
    ├── unit/                 # services with fake repos / fake LLM
    ├── integration/          # API + real Postgres (testcontainers)
    └── evals/                # golden CV/JD pairs to score prompt quality (run on demand)
```

Each module has the same shape:

```
modules/<feature>/
├── router.py      # HTTP only: parse, call service, map result → response schema
├── service.py     # business logic; no FastAPI imports; takes OrgContext explicitly
├── repository.py  # SQLAlchemy queries; every query filters by org_id
├── models.py      # SQLAlchemy ORM tables
├── schemas.py     # Pydantic request/response DTOs + LLM output schemas
└── tasks.py       # Procrastinate tasks for this feature (optional)
```

**Dependency rules** (enforced in CI with `import-linter`):
- `router → service → repository`. Routers never touch the DB or LLM directly.
- `modules/*` may import `core/*` and `ai/*`. Neither of those imports `modules/*`.
- One module uses another only through its `service.py`.

### 4.2 API conventions
- Prefix every route with `/api/v1`. Routes are resource nouns
  (`/candidates`, `/jobs`, `/fit-analyses`, `/screenings`, `/letters`,
  `/applications`).
- Async operations: `POST /api/v1/screenings` returns
  `202 {task_id, status_url}`, and clients poll `GET /api/v1/tasks/{id}`.
  Server-sent events can be added later.
- Errors use `application/problem+json` (RFC 9457) with a stable `code` field.
- List endpoints use cursor pagination (`?cursor=&limit=`).
- Uploads go to `POST /api/v1/documents` (multipart), which returns a
  `document_id`. Other endpoints then reference documents by id.
- Security limits: 10 MB max upload, an allowlist of MIME types checked by
  content (not only by extension), and the filename is never used as a
  storage path.

### 4.3 Data model (PostgreSQL)

Every tenant-owned table has `org_id UUID NOT NULL REFERENCES organizations`,
`created_at timestamptz`, and an index on `(org_id, created_at)`. Primary keys
are UUIDv7 (time-sortable).

| Table | Key columns | Notes |
|---|---|---|
| `organizations` | id, name, kind (`personal` \| `company`) | A candidate gets a personal org automatically at sign-up |
| `users` | id, firebase_uid, email, display_name | |
| `memberships` | org_id, user_id, role (`owner` \| `recruiter` \| `member`) | Unique on (org_id, user_id) |
| `documents` | id, org_id, kind (`cv` \| `jd` \| `letter_pdf` \| `attachment`), storage_key, mime, size, sha256, uploaded_by | The file bytes live in GCS |
| `candidate_profiles` | id, org_id, document_id, name, email, data JSONB, schema_version | `data` holds `CVInformation` |
| `job_postings` | id, org_id, source (`manual` \| `file` \| `france_travail`), external_id, title, company, data JSONB | Unique on (org_id, source, external_id) |
| `fit_analyses` | id, org_id, candidate_id, job_id, score, verdict, data JSONB, model, prompt_version | |
| `screenings` | id, org_id, job_id, status | One recruiter batch |
| `screening_results` | screening_id, candidate_id, fit_analysis_id, rank | |
| `letters` | id, org_id, candidate_id, job_id, language, tone, body, latex, pdf_document_id, status (`draft` \| `final`) | |
| `applications` | id, org_id, job_id NULL, company_name, source, status, applied_at, notes | |
| `application_events` | id, application_id, from_status, to_status, at, note | Status history for the tracker timeline |
| `job_search_cache` | key, provider, payload JSONB, expires_at | Replaces the second SQLite DB |
| `ai_calls` | id, org_id, feature, model, prompt_version, input_tokens, output_tokens, latency_ms, status | Usage and cost dashboard, quotas later |
| `procrastinate_*` | managed by the library | Task queue |

Later hardening: Postgres **Row-Level Security** on `org_id` as a second line of
defence behind the repository filters.

### 4.4 Auth and multi-tenancy
1. The frontend signs in with Firebase Auth (Google + email/password) and sends
   `Authorization: Bearer <ID token>`.
2. `core/auth.py` verifies the token (with `firebase-admin`, public keys
   cached) and upserts the `users` row, giving a `CurrentUser`.
3. The client sends `X-Org-Id` to pick the active org. `core/tenancy.py`
   checks the membership and returns `OrgContext(org_id, user_id, role)`. If
   the user is not a member, the request gets `404` (not `403`, so the org's
   existence isn't revealed).
4. Routes declare what they need, for example
   `ctx: OrgContext = Depends(require_role("recruiter"))`.
5. **Deleted:** tenant API keys in env vars, and credentials in query strings.
   Machine-to-machine API keys can come back later as a hashed `api_keys` table
   if needed.

### 4.5 AI layer
- `LLMGateway.generate(*, schema: type[T], system: str, user: str | list[Part], feature: str) -> T`
  uses Gemini **structured output** (`response_schema`), so there's no manual
  JSON parsing. PDFs and images can be passed as native parts, which may let
  some CVs skip text extraction.
- Every call is **stateless**. Agents no longer keep `conversation_history`. The
  only multi-turn flow (job search with tool calls) keeps its message list
  local to the task.
- Every call records to `ai_calls` with token counts, latency, model, and
  `prompt_version`.
- Retries with exponential backoff on 429 and 5xx. Per-call timeout.
  Per-org concurrency limit in the worker.
- **Prompt injection:** CV and JD text is untrusted. Wrap it in delimiters,
  tell the model to treat it as data, and validate outputs against the schema.
  The model gets no tools that write data.
- Models are set in `Settings` (`LLM_MODEL_FAST`, `LLM_MODEL_SMART`), not
  hard-coded.
- `tests/evals/` holds a small golden set (about 20 CV/JD pairs with expected
  score bands). Run it before changing a prompt or a model.

### 4.6 Background tasks
- **Procrastinate** tasks are defined per module in `tasks.py`, for example
  `matching.run_screening`, `letters.render_pdf`, `jobs.search_external`.
- The worker runs as a separate process (`procrastinate worker`), deployed as
  its own Cloud Run service with CPU always allocated and min instances = 1.
- The task is enqueued **in the same DB transaction** as the row that tracks
  it, so a task is never lost and never orphaned.
- Retries: 3 attempts with exponential backoff. A task that fails for good
  marks its domain row `failed` with an error code that is safe to show users.
- Task status goes through `GET /api/v1/tasks/{id}`, which reads the domain
  row, not the queue internals.

### 4.7 Documents and PDFs
- `Storage` protocol with `put`, `get`, `signed_url`, and `delete`.
  `GCSStorage` in prod, `LocalStorage` in dev and tests.
- Object keys: `orgs/{org_id}/{kind}/{document_id}`. Never derived from the
  user's filename.
- Downloads go through short-lived **signed URLs** after an authorization check.
- Letter PDFs: the worker renders the LaTeX template, compiles it with
  **Tectonic**, stores the PDF in GCS, and links it to `letters.pdf_document_id`.
  Drafts are regular `letters` rows with `status='draft'`. A GCS lifecycle rule
  deletes drafts after 7 days.

### 4.8 Cross-cutting
- **Config:** a single `Settings(BaseSettings)` with an `.env` file only in
  dev. Secrets come from Secret Manager in prod. The app fails fast at startup
  if config is invalid.
- **Logging:** JSON logs to stdout with `request_id`, `org_id`, `user_id`, and
  `task_id`. No file handlers; Cloud Logging collects stdout. Only the URL
  path is logged, never the query string.
- **Errors:** domain code raises `AppError` subclasses (`NotFound`,
  `Forbidden`, `ValidationFailed`, `UpstreamUnavailable`). One handler maps
  them to problem+json. Unhandled errors return a generic 500 and go to Error
  Reporting.
- **Testing:**
  - Unit tests use fake repositories and a fake `LLMGateway`.
  - Integration tests run against real Postgres via testcontainers.
  - One cross-tenant test per module (org A must never see org B's data).
  - Coverage target is ≥ 80% on `services`.
- **Quality gates:** `ruff check`, `ruff format --check`, `mypy --strict` on
  `src/`, `import-linter`, and `pytest`.

---

## 5. Frontend

```
frontend/
├── package.json            # pnpm
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── app/                # router, providers (QueryClient, Auth), layout shell
│   ├── lib/
│   │   ├── api/            # generated schema.d.ts + openapi-fetch client + auth header
│   │   ├── auth.ts         # Firebase Auth wrapper
│   │   └── utils.ts
│   ├── components/ui/      # shadcn/ui primitives
│   └── features/
│       ├── candidate/      # upload CV, pick job, fit report, interview kit
│       ├── recruiter/      # requisitions, bulk upload, screening table, outreach drafts
│       ├── letters/        # split-screen editor + PDF preview
│       ├── tracker/        # applications board/table + timeline
│       └── job-search/     # France Travail search
└── tests/                  # Vitest + Testing Library; Playwright for e2e smoke
```

- **Stack:** React 19, TypeScript (strict), Vite, React Router, TanStack Query
  (server state and polling of async tasks), react-hook-form + zod (forms),
  Tailwind CSS v4 (built), shadcn/ui, and react-pdf for previews.
- **API types** are generated by `pnpm gen:api` from FastAPI's `/openapi.json`.
  CI fails if the generated file is out of date.
- **Why not Next.js:** the app sits behind a login, has no SEO needs, and is
  already served by a Python API. A static SPA is simpler and cheaper to host.
- **Hosting:** Firebase Hosting serves the built SPA and rewrites `/api/**` to
  the Cloud Run API, so everything is same-origin and needs no CORS setup.
  FastAPI stops serving HTML and JS.

---

## 6. Environments and delivery

| | Local dev | Production |
|---|---|---|
| API | `uv run fastapi dev` | Cloud Run `recruitai-api` |
| Worker | `uv run procrastinate worker` | Cloud Run `recruitai-worker` (always-on CPU) |
| DB | Postgres in `docker compose` | Cloud SQL Postgres 16 (private IP, automated backups) |
| Files | `LocalStorage` (`./.data`) | GCS bucket (uniform access, lifecycle rules) |
| Auth | Firebase Auth emulator | Firebase Auth / Identity Platform |
| LLM | Gemini API key | Vertex AI via the service's workload identity (no key files) |
| Frontend | `pnpm dev` (Vite proxy `/api` → :8000) | Firebase Hosting |
| Secrets | `.env` (gitignored) | Secret Manager |

- **Docker:** multi-stage build using the official `ghcr.io/astral-sh/uv`
  image. Runs as a non-root user. The API image and the worker image are
  separate; only the worker needs Tectonic. No Rust toolchain.
- **CI (GitHub Actions) on every PR:**
  - backend: `ruff`, `mypy`, `import-linter`, `pytest` (with a Postgres service)
  - frontend: `tsc`, `eslint`, `vitest`, `build`
  - an OpenAPI drift check
- **CD on merge to `main`:**
  1. Build images and push to Artifact Registry.
  2. Run `alembic upgrade head` as a Cloud Run job.
  3. Deploy the API and the worker.
  4. Deploy the frontend.
- **Branching:** short-lived feature branches merged into `main` through PRs.
  Retire the long-lived `develop` / `dev-frontend` branches.

---

## 7. Migration plan

**Rebuild in place, feature by feature. No from-scratch rewrite.** The prompts
and schemas carry over. Everything around them is replaced. Each phase ends
with a green CI run and a working app.

| Phase | Work | Exit criteria |
|---|---|---|
| **0. Foundations** | New `backend/src/recruitai` skeleton, `Settings`, fixed `pyproject.toml` (remove `genai` / `vertexai` / `dotenv` / `path`; add `google-genai`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `procrastinate`, `pydantic-settings`, `firebase-admin`, `google-cloud-storage`; move pytest to a dev group), ruff, mypy, pre-commit, GitHub Actions, `docker compose` with Postgres | `create_app()` boots, `/health` is green, CI runs |
| **1. Core platform** | `core/db` + first Alembic migration (identity tables), Firebase auth + `OrgContext`, `Storage`, error handling, logging, `LLMGateway` + `ai_calls`, Procrastinate worker + `/tasks/{id}` | Sign in, create an org, upload a file, run a dummy task end to end, with tests |
| **2. Port features** | In order: `documents` + `candidates` → `jobs` (incl. France Travail, cache table) → `matching` (fit + screenings) → `letters` (Tectonic) → `applications`. Each one moves its prompts and schemas and gets a cross-tenant test | Every old endpoint has a `/api/v1` equivalent with tests |
| **3. Frontend rebuild** | Vite/React app, auth, generated client. Screens in the same order as phase 2 | Feature parity with the current UI |
| **4. Production** | GCP project setup (Cloud SQL, GCS, Secret Manager, Cloud Run ×2, Firebase Hosting), CD pipeline, alerts on 5xx rate and task failures | Deployed from `main` with no manual steps |
| **5. Cleanup** | Delete `api/`, `application/`, `domain/`, `infrastructure/`, `workers/`, `migrations/`, old `frontend/*.js`, and the old Dockerfile | Only the new structure remains |

Existing SQLite data is dev-only, so no data migration is planned. If some of
it must be kept, a one-off import script can go in phase 2.

---

## 8. Open questions (decide before phase 1)

1. **Who is the primary customer:** job seekers (B2C), recruiting teams (B2B),
   or both from day one? The design supports both through personal and company
   organizations. The answer decides which half of the UI gets built first.
2. **Auth provider:** Firebase Auth is recommended because the rest of the
   stack is on GCP. The self-hosted alternative is `fastapi-users` with JWT,
   which means no vendor but you own password resets, email verification,
   and OAuth.
3. **Letters:** keep LaTeX as the editable format (recommended; it keeps the
   co-writing feature), or move to a simpler Markdown-to-PDF flow?
4. **Data retention for CVs (GDPR):** how long uploads and extracted profiles
   are kept, and whether candidates can delete their own data. This affects
   the storage lifecycle rules and adds a `DELETE /me` flow.

---

## 9. Architecture decision records

When a decision in this document changes, add a short ADR to `adr/NNNN-title.md`
(context → decision → consequences). The initial set is the rows in §1.
