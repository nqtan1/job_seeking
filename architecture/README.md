# RecruitAI Architecture Handbook

This folder explains **how RecruitAI is designed and why**. With it you can
make decisions about the app yourself, review code written by anyone (human or
AI), and tell when a change goes against the design.

[`../ARCHITECTURE.md`](../ARCHITECTURE.md) is the **specification**: what we
build. This folder is the **reasoning**: why we build it that way, what it
costs, and when to change our minds.

---

## Reading order

| # | Document | Read it to understand | Time |
|---|---|---|---|
| 1 | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | The target design: stack, modules, data model, plan | 25 min |
| 2 | [`01-system-walkthrough.md`](01-system-walkthrough.md) | How a request flows through the system, step by step, for each main feature | 30 min |
| 3 | [`decisions/`](decisions/) | **Why each technology was chosen over the alternatives** (one decision record per choice) | 60 min |
| 4 | [`02-phases.md`](02-phases.md) | Each rebuild phase: goal, **strengths, weaknesses**, risks, exit criteria, effort | 30 min |
| 5 | [`03-risks-and-costs.md`](03-risks-and-costs.md) | Risk register, monthly cost model, scaling limits, vendor lock-in | 20 min |
| 6 | [`04-operations-and-security.md`](04-operations-and-security.md) | Running it in production: config, deploys, migrations, monitoring, incidents, security checklist | 25 min |
| 7 | [`05-glossary.md`](05-glossary.md) | Every technical term used in these documents, in plain words | as needed |

---

## The whole design in one page

**What the product is (v1):** a personal job-application assistant for
individual job seekers. You upload your CV once, collect jobs, get a fit
report, write tailored letters in a writing studio, and track your
applications. Recruiter features come later.

**How it is built:**

```
Browser (React SPA)
   │  signs in with Firebase Auth (Google account), gets an ID token
   ▼
Firebase Hosting  ──/api/**──►  Cloud Run "api" (FastAPI, Python)
                                   │  verifies token → user → personal org
                                   │  router → service → repository
                                   ├──► Cloud SQL (PostgreSQL): all structured data + task queue
                                   ├──► Cloud Storage: files (CVs, PDFs)
                                   └──► Vertex AI Gemini: short AI calls
Cloud Run "worker" (same code, other entrypoint)
   └── picks tasks from Postgres: PDF rendering, exports, long AI jobs, cleanup
```

**The five rules that keep it clean.** If a pull request breaks one of these,
it is wrong, even if it works:

1. **No state inside a container.** Data lives in Postgres, files live in
   Cloud Storage. A container can be killed at any time without losing
   anything.
2. **The tenant comes from the login token, never from the request.** Every
   database query filters by `org_id`.
3. **Routers only translate HTTP; services hold the logic; repositories hold
   the SQL.** A service never imports FastAPI. A router never runs SQL or
   calls the LLM.
4. **One feature, one folder** (`modules/<feature>/`). Modules talk to each
   other only through `service.py`.
5. **Slow or failure-prone work goes to the worker.** The API answers in
   under a few seconds, or it returns a task id.

---

## Decision index

| ID | Decision | Status |
|---|---|---|
| [0001](decisions/0001-rebuild-incrementally.md) | Rebuild incrementally in place (no big-bang rewrite) | Accepted |
| [0002](decisions/0002-modular-monolith.md) | Modular monolith, not microservices | Accepted |
| [0003](decisions/0003-python-fastapi.md) | Keep Python + FastAPI for the backend | Accepted |
| [0004](decisions/0004-postgresql-sqlalchemy-alembic.md) | PostgreSQL + SQLAlchemy 2.0 + Alembic | Accepted |
| [0005](decisions/0005-task-queue-procrastinate.md) | Postgres-backed task queue (Procrastinate) | Accepted, with a named fallback |
| [0006](decisions/0006-object-storage-gcs.md) | Files in Cloud Storage behind a `Storage` interface | Accepted |
| [0007](decisions/0007-auth-firebase.md) | Firebase Authentication | Accepted |
| [0008](decisions/0008-tenancy-personal-org.md) | Every user gets a personal organization (`org_id` everywhere) | Accepted |
| [0009](decisions/0009-llm-gateway-google-genai.md) | Direct `google-genai` SDK behind an `LLMGateway`, no LangChain | Accepted |
| [0010](decisions/0010-letters-structured-latex-tectonic.md) | Letters as structured content, rendered with LaTeX via Tectonic | Accepted |
| [0011](decisions/0011-frontend-react-vite.md) | React + TypeScript + Vite single-page app | Accepted |
| [0012](decisions/0012-api-contract-openapi-codegen.md) | Typed API client generated from OpenAPI | Accepted |
| [0013](decisions/0013-hosting-cloud-run-firebase.md) | Cloud Run + Firebase Hosting on Google Cloud (EU region) | Accepted |
| [0014](decisions/0014-privacy-retention.md) | Privacy-first data retention policy | Accepted |

To change a decision, copy [`decisions/0000-template.md`](decisions/0000-template.md),
write the new record, and mark the old one **Superseded by NNNN**. Never
delete old records. They are the history of *why* the app looks the way it
does.

---

## How to use these documents to stay in control

- **Before starting a feature:** find the module it belongs to
  ([walkthrough §6](01-system-walkthrough.md#6-where-to-change-what)). If it
  doesn't fit any module, that's a design question. Answer it here first.
- **When reviewing a PR** (including AI-written code): check the five rules
  above and the [review checklist](04-operations-and-security.md#8-code-review-checklist).
- **When something feels slow or expensive:** check the "when to reconsider"
  section of the related decision. Each one says what signal means the
  decision should change.
- **When you're asked "why not X?":** the decision records list the
  alternatives we rejected and why.
