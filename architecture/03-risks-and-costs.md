# 03 · Risks, Costs, Scaling Limits, Lock-in

---

## 1. Risk register

Likelihood and impact use the scale **L**ow / **M**edium / **H**igh.

| # | Risk | L | I | Mitigation | Early warning signal |
|---|---|---|---|---|---|
| R1 | **Scope creep during the rebuild:** new features mixed into porting, and the rebuild never finishes | H | H | Porting PRs and feature PRs are separate; the letter studio v1 feature list is fixed; phase exit criteria | A phase exceeds its estimate by more than 50% |
| R2 | **Cross-tenant data leak:** one user sees another's CV | L | H | `OrgContext` from the token only; `org_id` required in repositories; a cross-tenant test per module; RLS later | A test that doesn't use `OrgContext`; a query without `org_id` in review |
| R3 | **AI cost runaway** (abuse, loops, a big batch) | M | M–H | App Check; per-user daily quotas stored with `ai_calls`; `fast` model by default; budget alerts; max input size | Daily AI spend alert; one user above the p99 of calls |
| R4 | **AI output quality regression** after a prompt or model change | M | M | Versioned prompts; eval set run before merge; `prompt_version` stored on every result | Eval score drops; users regenerating more often |
| R5 | **Hallucinated claims in letters** (inventing experience) | M | H (user trust, and harm to the user's application) | Grounding check against the profile; unsupported claims highlighted; the user must review before export | Grounding warnings per letter |
| R6 | **Prompt injection** via CV/JD text ("ignore instructions…") | M | L–M | Untrusted text inside delimiters; schema-validated output; the model has no write tools; outputs are shown, never executed | Schema validation failures; weird outputs in evals |
| R7 | **LaTeX raw mode abused** (shell escape, file read) | L | H | Tectonic with no shell-escape, sandboxed temp dir, timeout and memory limits, forbidden-command check | Render timeouts; blocked-command logs |
| R8 | **Personal data in logs** | M | M | Structured logging with an allowlist of fields; no request bodies; no query strings; a review checklist item | A log search for `@` or CV keywords in staging |
| R9 | **Vendor outage** (Vertex, France Travail) | M | M | Retries with backoff; tasks retry later; clear "temporarily unavailable" UX; 24 h job cache | Upstream error rate alert |
| R10 | **First production deploy surprises** (IAM, networking, offline Tectonic) | H | M | Deploy "hello world" through the full pipeline in P1/P2 (see 02-phases P4) | — |
| R11 | **Bus factor = 1:** only you understand the system | H | H | This handbook; ADRs; CLAUDE.md for AI tools; conventions enforced by CI | Parts of the code that you can't explain |
| R12 | **Regulatory change** (EU AI Act timeline, GDPR interpretation) | M | M (B2C) / H (B2B) | B2C first (not high-risk); new ADR before B2B; legal review before launch | Official guidance updates |
| R13 | **Fixed costs before revenue** | H | L–M | Smallest instances; scale-to-zero API; the Cloud Tasks fallback documented | Monthly bill vs budget |

---

## 2. Monthly cost model (estimate)

> **These are order-of-magnitude estimates, not quotes.** Cloud prices change
> and depend on region and configuration. Check with the
> [Google Cloud pricing calculator](https://cloud.google.com/products/calculator)
> before committing, and set budget alerts from day one.

### 2.1 Fixed costs (paid even with zero users)

| Item | Configuration | Rough monthly cost |
|---|---|---|
| Cloud SQL Postgres | Smallest shared-core instance, 10 GB SSD, automated backups | ~10–30 € |
| Cloud Run worker | 1 instance always on, small CPU/memory | ~15–50 € |
| Cloud Run API | min instances 0 (scale to zero) | ~0 € idle |
| Firebase Hosting, Auth, App Check | Within free tiers at MVP scale | ~0 € |
| GCS, Secret Manager, Scheduler, Logging | Tiny volumes | ~0–5 € |
| Domain name | | ~1 € |
| **Total fixed** | | **~30–85 € / month** |

**Ways to cut fixed costs early (trade-offs in parentheses):**
- Staging DB on a free Postgres tier (Neon or Supabase). The code is the same.
  (Staging differs slightly from prod.)
- Cloud Tasks instead of an always-on worker (ADR 0005 fallback). (Lose
  transactional enqueueing and add an outbox table.)
- Stop the staging Cloud SQL instance when you aren't using it.

### 2.2 Variable costs (grow with users)

| Driver | What scales it | Notes |
|---|---|---|
| **Gemini (Vertex AI)** | Tokens per action × actions per user | Usually **the biggest variable cost**. A CV extraction or fit report on a "flash"-class model typically costs well under a cent to a few cents. Measure it with `ai_calls` from day one |
| Cloud Run API CPU | Requests × duration | Most time is spent *waiting* on Gemini. Use concurrency > 1 (for example 40–80) so one instance handles many waiting requests |
| Cloud SQL | Storage + a bigger instance when CPU is saturated | JSONB profiles are small (KBs) |
| GCS | CV and PDF storage (MBs per user) + egress on downloads | Lifecycle rules keep it bounded |
| Email (reminders) | Emails per month | Providers have free tiers for low volumes |

**Unit economics to track** (from `ai_calls`): the AI cost per active user per
month. That number decides pricing, whether you can offer a free tier, and
what quotas to set.

---

## 3. Scaling limits: what breaks first, and the fix

| Load level (rough) | First bottleneck | Fix | Architecture change? |
|---|---|---|---|
| 0–1k users | None. Cold starts are the only visible issue | API min instances = 1 | No |
| 1k–10k users | Gemini quota (requests per minute) and cost | Request a Vertex quota increase; move heavy calls to the worker with per-org concurrency limits; cache fit reports | No |
| 10k–50k users | Cloud SQL connections (API instances × pool size) | Tune pool sizes; bigger instance; PgBouncer or the Cloud SQL managed connection pooler | No |
| 50k+ users | DB CPU on heavy lists and searches; queue throughput | Indexes, read replica, move the queue to Cloud Tasks or Redis | Small (swap behind `core/tasks.py`) |
| Very large | A single module's needs diverge (for example, rendering) | Extract that module into its own Cloud Run service | Planned for by ADR 0002 |

The architecture has **no rewrite cliff** until far beyond B2C MVP scale. Every
step up is configuration or a local swap behind an interface.

---

## 4. Vendor lock-in map

What's portable and what would be work to move away from Google.

| Component | Lock-in | Exit path | Exit effort |
|---|---|---|---|
| Backend code (FastAPI container) | None | Runs on any container platform | Hours |
| PostgreSQL | None | `pg_dump` → any Postgres (AWS RDS, Supabase, Neon, self-hosted) | Hours–days |
| Task queue (Procrastinate) | None (it's in Postgres) | Moves with the DB | — |
| Files (GCS) | Low | `Storage` interface: write an S3 implementation, copy the bucket | Days |
| LLM (Gemini) | Medium | `LLMGateway`: add a provider implementation, **re-run the evals** (prompts may need tuning) | Days–weeks |
| **Auth (Firebase)** | **Medium–High** | Export users (including password hashes) with Firebase's tools and import them into the new provider, or force password resets; Google sign-in users simply sign in again | Weeks |
| Hosting (Cloud Run, Firebase Hosting) | Low | Any container host + any static host | Days |
| Infra (Terraform) | Medium | The Terraform is GCP-specific; rewrite for the new cloud | Weeks |

**Conclusion:** the only "sticky" choice is auth, which is standard for SaaS
and is the price of not building auth yourself (ADR 0007). Everything else is
behind an interface or a standard protocol.

---

## 5. Deliberate non-goals (things this architecture does NOT do, on purpose)

| Non-goal | Why not now | When it would change |
|---|---|---|
| Microservices / Kubernetes | Operational cost with no benefit for one developer | Multiple teams (ADR 0002) |
| Real-time collaboration (multiple people editing one letter) | B2C is single-user | B2B with shared workspaces |
| Offline or mobile native apps | The web SPA covers the need | Proven demand; the OpenAPI contract is ready for it |
| Multi-region / high availability across regions | Cost; EU single-region is fine for the MVP | SLAs for B2B customers |
| RAG / vector database | No use case yet; a user's documents fit in the model's context | A "search my past letters/jobs" feature at scale; Postgres `pgvector` first |
| Self-hosted LLMs | Cost, quality and operations burden | Strict data-sovereignty customers |
| Event sourcing / CQRS | Complexity with no v1 need; `application_events` covers the history that matters | Probably never for this product |
