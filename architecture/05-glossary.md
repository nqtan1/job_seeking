# 05 · Glossary

Plain-language definitions of the terms used in this handbook.

| Term | Meaning | Where it matters here |
|---|---|---|
| **ADR** (Architecture Decision Record) | A short document recording one decision: context, options, choice, consequences | `decisions/` |
| **Alembic** | Tool that creates and applies **database migrations** for SQLAlchemy | ADR 0004, Ops §4 |
| **App Check** | A Firebase feature that proves requests come from your real app, not a script | Protects AI endpoints from abuse |
| **Async / event loop** | Python runs many waiting tasks on one thread; blocking code on that thread freezes everything | Run blocking libraries in threads |
| **Backfill** | Filling a new column for existing rows after adding it | Expand/contract migrations |
| **Cold start** | Delay when Cloud Run starts a new container because none were running | API min instances |
| **Cloud Run** | Google service that runs containers, scaling them automatically (down to zero) | API + worker hosting |
| **Cloud SQL** | Google's managed PostgreSQL (backups, patches, high availability options) | Main database |
| **Connection pool** | A set of reusable DB connections kept open by each process | Pool size × instances < DB max |
| **CSP** (Content Security Policy) | A browser header limiting which scripts, styles and hosts a page may load | Web security checklist |
| **Cross-tenant test** | A test proving user/org A can't read or modify org B's data | One per module |
| **DPA** (Data Processing Addendum) | A contract where a provider (e.g. Google) commits to how it processes your users' data | Accept Google Cloud's before launch |
| **Eval set** | A fixed set of inputs with expected qualities, used to measure AI output before and after changes | `tests/evals/` |
| **Expand / contract** | A migration style where you first add (expand), then remove old parts (contract) later, so old and new code both work during deploys | Ops §4 |
| **Firebase Auth** | Google's hosted login service: issues **ID tokens** after sign-in | ADR 0007 |
| **Grounding check** | Verifying that each claim in generated text is supported by source data (the user's profile) | Letter studio, risk R5 |
| **IAM** | Identity and Access Management: who (people or service accounts) can do what on which resource | Least-privilege service accounts |
| **ID token / JWT** | A signed token saying "this is user X", valid about 1 hour; the backend verifies its signature | `core/auth.py` |
| **Idempotent** | Running an operation twice has the same effect as once. Tasks should be, because they can be retried | Worker tasks |
| **import-linter** | A tool that fails CI when code imports across forbidden boundaries | Enforces module rules |
| **JSONB** | PostgreSQL's binary JSON column type; indexable and queryable | AI outputs, letter content |
| **Lifecycle rule** | A GCS setting that automatically deletes objects after N days | Retention enforcement |
| **LLMGateway** | Our small interface for calling the language model; hides the vendor SDK | ADR 0009 |
| **Migration** | A versioned script that changes the database schema | Alembic |
| **Modular monolith** | One deployable application internally split into strict feature modules | ADR 0002 |
| **Multi-tenancy** | One system serving many isolated customers (tenants) | `org_id` model, ADR 0008 |
| **N+1 query** | A bug where code runs 1 query for a list, then 1 more per item | Use `selectinload` |
| **OpenAPI** | A machine-readable description of an HTTP API; FastAPI generates it automatically | Typed frontend client, ADR 0012 |
| **Org / organization** | The tenant. In v1 every user has exactly one, personal and invisible | `organizations` table |
| **`OrgContext`** | The object every request carries: `org_id`, `user_id`, `role`, derived from the token | `core/tenancy.py` |
| **Outbox pattern** | Writing "messages to send" into your DB in the same transaction, then sending them separately; restores atomicity with external queues | Needed only if we switch to Cloud Tasks |
| **p95 latency** | 95% of requests are faster than this value | Alerts |
| **PITR** (Point-In-Time Recovery) | Restoring the DB to any moment within the retention window | Cloud SQL backups |
| **Problem+json** (RFC 9457) | A standard JSON format for HTTP error responses | `core/errors.py` |
| **Procrastinate** | A Python task-queue library that stores jobs in PostgreSQL | ADR 0005 |
| **Prompt injection** | Malicious text in input trying to override the AI's instructions | Risk R6 |
| **Prompt version** | An identifier (e.g. `cv_extract@3`) stored with each AI result so you know which prompt produced it | `ai/prompts/` |
| **Pydantic** | Python library for typed data models + validation; source of API, OpenAPI and LLM schemas | Everywhere in the backend |
| **Repository (pattern)** | The layer containing all DB queries for a module | `repository.py` |
| **RLS** (Row-Level Security) | PostgreSQL feature that filters rows per session automatically; a second safety net for tenancy | Later hardening |
| **Scale to zero** | No containers running (and no compute cost) when there's no traffic | Cloud Run API |
| **Secret Manager** | Google service storing secrets (API keys, passwords) with access control and audit | Config §2 |
| **Service (layer)** | The layer containing business logic; no HTTP, no SQL | `service.py` |
| **Service account** | A non-human Google identity that a Cloud Run service runs as | No key files |
| **Signed URL** | A temporary link granting access to one private file | Downloads from GCS |
| **SPA** (Single-Page Application) | A web app that loads once and renders screens in the browser | React frontend |
| **SQLAlchemy** | Python's standard ORM / SQL toolkit | ADR 0004 |
| **Structured output** | Asking the LLM to return JSON that matches a given schema | `LLMGateway.generate(schema=…)` |
| **Tectonic** | A self-contained LaTeX engine distributed as one binary | Letter PDFs, ADR 0010 |
| **Terraform** | Infrastructure as code: describe cloud resources in files, apply them reproducibly | `infra/`, phase 4 |
| **Testcontainers** | A library that starts real services (Postgres) in Docker for tests | Integration tests |
| **Transactional enqueue** | Creating a background job in the same DB transaction as the data change it relates to | Why the queue is in Postgres |
| **UUIDv7** | A time-ordered unique ID; sorts by creation time and indexes well | Primary keys |
| **Vertex AI** | Google Cloud's enterprise AI platform (Gemini with enterprise data terms, EU regions) | Production LLM |
| **Workload Identity Federation** | Lets GitHub Actions act as a Google service account without stored keys | CD pipeline |
