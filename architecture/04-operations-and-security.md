# 04 · Operations & Security Guide

How to run, change, deploy, observe, and protect RecruitAI in production.

---

## 1. Environments

| | `local` | `staging` | `prod` |
|---|---|---|---|
| Purpose | Development | Test deploys, demos, migrations dry run | Real users |
| GCP project | none (docker compose) | `recruitai-staging` | `recruitai-prod` |
| Data | Fake/seed data only | Fake data only | Real data. **Never copied to other environments** |
| LLM | Gemini API key (fake data only) or Vertex | Vertex | Vertex |
| Auth | Firebase emulator | Firebase (staging project) | Firebase (prod project) |
| Deploys | — | Every merge to `main` | Tag or manual approval |

**Rule:** production personal data never leaves prod. To debug, reproduce with
fake data or anonymized fixtures.

---

## 2. Configuration

All config lives in `Settings` (pydantic-settings). The app **refuses to start**
if a required value is missing or invalid.

| Variable | Example | Secret? | Notes |
|---|---|---|---|
| `ENV` | `local` / `staging` / `prod` | no | Switches some safe defaults (for example, the API docs are disabled in prod) |
| `DATABASE_URL` | `postgresql+asyncpg://…` | yes (prod) | In prod, IAM auth via the Cloud SQL connector is preferred (no password) |
| `DB_POOL_SIZE` | `5` | no | (Pool × instances) must stay below the DB's connection limit |
| `STORAGE_BACKEND` | `local` / `gcs` | no | |
| `GCS_BUCKET` | `recruitai-prod-files` | no | |
| `LLM_BACKEND` | `vertex` / `api_key` | no | `api_key` is **forbidden** when `ENV=prod` (validated at startup) |
| `GOOGLE_CLOUD_PROJECT`, `VERTEX_LOCATION` | `recruitai-prod`, `europe-west1` | no | |
| `LLM_MODEL_FAST`, `LLM_MODEL_SMART` | model ids | no | Change models without code |
| `GEMINI_API_KEY` | | yes | Local only |
| `FIREBASE_PROJECT_ID` | | no | |
| `FRANCE_TRAVAIL_CLIENT_ID` / `_SECRET` | | yes | Secret Manager |
| `AI_DAILY_QUOTA_PER_USER` | `100` | no | Protects against cost runaway |
| `LOG_LEVEL` | `INFO` | no | |

Secrets live in **Secret Manager** and are mounted as env vars by Cloud Run.
`.env` files are only for local use and are gitignored. The repo keeps an
`.env.example` up to date.

---

## 3. Deploying

```
PR opened ─► CI: ruff · mypy · import-linter · pytest (Postgres) · frontend tsc/eslint/vitest/build · OpenAPI drift check
merge to main ─► build images (api, worker) ─► push to Artifact Registry
             ─► run "migrate" Cloud Run job (alembic upgrade head) on staging
             ─► deploy api + worker to staging ─► deploy frontend to staging hosting
             ─► smoke test (Playwright against staging)
tag vX.Y.Z  ─► same steps on prod (with manual approval)
```

**Rollback:** Cloud Run keeps previous revisions, so shift traffic back to the
last good revision (seconds). The frontend has the same option (Firebase
Hosting rollback). **Database migrations are not rolled back.** They're
written to be backward compatible (next section), so the old code keeps
working on the new schema.

---

## 4. Database migrations: the rules

1. **Every schema change is an Alembic revision**, reviewed in the PR. Read
   autogenerate output before committing; it isn't always right.
2. **Expand, then contract.** The old code and the new code must both work
   during a deploy:
   - Add a column as nullable or with a default → deploy code that writes it →
     backfill → make it NOT NULL in a later migration.
   - Rename = add new column → dual-write → migrate reads → drop the old one
     later.
   - Never drop a column in the same deploy as the code that stops using it.
3. **Watch for long locks:** use `CREATE INDEX CONCURRENTLY` on large tables
   (Alembic: `postgresql_concurrently=True` outside a transaction).
4. **JSONB fields** (CV profile, fit data, letter content) evolve **without
   migrations**, using `schema_version` + tolerant readers. Bump the version
   when the Pydantic schema changes incompatibly.

---

## 5. Observability

| Signal | Where | Alert threshold (starting point) |
|---|---|---|
| Structured logs (JSON: `request_id`, `org_id`, `user_id`, `task_id`, `event`) | Cloud Logging | — |
| Unhandled exceptions | Error Reporting | Any new error type → email |
| API 5xx rate | Cloud Monitoring | > 2% over 5 min |
| API p95 latency | Cloud Monitoring | > 5 s over 10 min (AI calls included) |
| Failed tasks | Log-based metric on `task_failed` | > 5 per hour |
| Queue backlog | SQL query on the Procrastinate tables (exported metric) | > 50 jobs waiting > 5 min |
| Cloud SQL CPU / storage / connections | Cloud Monitoring | CPU > 80% for 15 min; storage > 80%; connections > 80% of max |
| AI spend | `ai_calls` daily sum + GCP budget alerts | 50% / 90% / 100% of the monthly budget |

**How to trace one user's problem:** get the `request_id` from the response
header `X-Request-Id` (the frontend shows it in error dialogs). Filter Cloud
Logging by it to see every log line for that request, including tasks it
enqueued (which carry the same correlation id).

---

## 6. Incident basics (a one-person runbook)

1. **Is it us or a vendor?** Check the Google Cloud status page and the
   Vertex / France Travail error rates in the logs.
2. **Recent deploy?** Roll back the Cloud Run revision first, investigate
   second.
3. **DB problem?** Check connections and CPU. Kill runaway queries
   (`pg_stat_activity`). Scale the instance up temporarily.
4. **Cost spike?** Find the top orgs by `ai_calls` in the last 24 h. Lower
   `AI_DAILY_QUOTA_PER_USER`. Block the abusive account.
5. **Data exposure suspected?** Stop the leak (roll back or disable the
   endpoint), keep the logs, assess scope. **GDPR: notify the CNIL within
   72 h** if personal data was breached and there's a risk to people.
6. Write a short post-incident note: what happened, why, and the fix that
   prevents it (often a new test or alert).

**Backups:** Cloud SQL automated daily backups + point-in-time recovery
(7-day window). **Test a restore into staging before launch, then every
quarter.** A backup you've never restored isn't a backup.

---

## 7. Security checklist

**Identity and access**
- [ ] Every non-public endpoint depends on `OrgContext`. There's a test that
      lists all routes and asserts this.
- [ ] Token revocation is checked on sensitive endpoints (delete account,
      export).
- [ ] App Check is enforced on AI endpoints.
- [ ] Cloud Run service accounts have least-privilege roles only. No JSON keys
      exist; CI uses Workload Identity Federation.

**Input and files**
- [ ] Upload limits: size ≤ 10 MB; MIME sniffed from bytes; allowlist
      (PDF, DOCX, TXT, PNG, JPEG).
- [ ] Storage keys never contain user input.
- [ ] PDFs are parsed in the worker or with timeouts (malformed PDFs can hang
      parsers).
- [ ] Tectonic runs without shell-escape, in a temp dir, with timeout and
      memory limits. Raw LaTeX is checked for forbidden commands.

**Data protection**
- [ ] Logs contain no bodies, no query strings, no emails, no CV or letter
      text.
- [ ] The GCS bucket has no public access and uniform bucket-level access;
      downloads use signed URLs that expire in ≤ 15 min.
- [ ] Cloud SQL has a private IP and IAM auth; TLS is enforced.
- [ ] Data stays in the EU region: Vertex location = the same EU region.
- [ ] The export and delete flows are tested end to end, including GCS
      objects and backup expiry.

**AI-specific**
- [ ] Untrusted text is wrapped in delimiters with a "treat as data"
      instruction.
- [ ] Outputs are validated against a Pydantic schema; invalid output → retry
      once → a clean error.
- [ ] Letters: unsupported claims are flagged (grounding check) before export.
- [ ] Per-user daily quota and max input size are enforced.

**Web**
- [ ] Security headers on Hosting: CSP, HSTS, `X-Content-Type-Options`,
      `Referrer-Policy`.
- [ ] No CORS (same origin through the Hosting rewrite).
- [ ] Rate limiting on auth-adjacent and AI endpoints.
- [ ] Dependencies scanned (Dependabot / `pip-audit` / `pnpm audit`) in CI.

---

## 8. Code review checklist

Use this on every PR, including code written by an AI assistant. A "no"
answer is a request for changes.

**Architecture**
1. Is the code in the right module (`modules/<feature>/`)? Does it import
   another module only through `service.py`?
2. Does the router contain only HTTP concerns (no SQL, no LLM calls, no
   business rules)?
3. Is the service free of FastAPI imports?
4. Does every repository query filter by `org_id`?

**Data**

5. Is a schema change done through an Alembic migration that follows
   expand/contract?
6. Are new async DB relationships loaded explicitly (`selectinload`), not
   lazily?

**Work and AI**

7. Is any slow (> about 5 s) or retryable work a task instead of inline?
8. Do AI calls go through `LLMGateway` with a `feature` name and a versioned
   prompt?
9. Did the eval set run if a prompt or model changed?

**Security and privacy**

10. Is nothing personal logged?
11. Is there a cross-tenant test for new endpoints that read or write data?
12. Is blocking code (pdfplumber, SDK sync calls) run in a thread, not on the
    event loop?

**Contract and tooling**

13. Is `response_model` declared, and was the frontend client regenerated?
14. Are there tests for the happy path + the main failure path?
15. Is `.env.example` updated if a new setting was added?
