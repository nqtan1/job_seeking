# 0013 · Cloud Run + Firebase Hosting on Google Cloud (EU region)

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §6 and §9

## Context
The owner wants to deploy on Google services. Vertex AI is already used.
Traffic is unknown and probably low and bursty at first. Users are mostly in
France and the EU (France Travail integration), and the data is personal
(CVs), so it should stay in the EU.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Compute Engine VM** (+ docker compose) | Cheapest at constant load; full control | You patch the OS, handle TLS, scaling, restarts and backups yourself; a single point of failure |
| **GKE (Kubernetes)** | Maximum flexibility | Heavy operations and cost for one developer; complexity with no payoff at this size |
| **App Engine** | Managed | Older platform; less flexible than Cloud Run; containers are second-class |
| **Render / Fly.io / Railway / Vercel** | Great developer experience | Outside GCP (separate billing, IAM, and data processor); Vertex access needs keys; EU residency varies |
| **Cloud Run (API + worker) + Firebase Hosting** ✅ | Containers, HTTPS and autoscaling managed; **API scales to zero**; IAM service identity means no key files; same project as Vertex, Cloud SQL, GCS and Firebase; EU regions | Cold starts (about 1–3 s for Python) when scaled to zero; the always-on worker costs money; some GCP concepts to learn (IAM, VPC connector) |

**Region:** `europe-west1` (Belgium) is the broadest service availability and
among the cheapest EU regions. `europe-west9` (Paris) keeps data in France
but has fewer services. **Before choosing, check that Vertex AI Gemini models
are offered in that region.** Put everything in the same region.

## Decision
- Cloud Run service `recruitai-api` (min instances 0, raised to 1 when real
  users arrive, to avoid cold starts)
- Cloud Run `recruitai-worker` (always on)
- Cloud SQL, GCS and Vertex in the same EU region
- Firebase Hosting for the SPA, with a `/api/**` rewrite to Cloud Run (same
  origin, no CORS)
- Secret Manager for secrets
- Terraform in `infra/` from phase 4

## Why
It's the lowest-operations option that runs our containers unchanged, keeps
everything in one cloud account with IAM-based auth, and costs close to
nothing when idle, except for the database and the worker.

## Consequences
- **Good:** no servers to patch; deploy is `gcloud run deploy` or CI; logs,
  metrics and errors are centralized.
- **Bad:**
  - Cold starts on the API while scaled to zero.
  - Cloud Run request timeout: keep sync endpoints short, as the design
    already does.
  - GCP lock-in for hosting, but the containers stay portable (see
    [03-risks-and-costs §4](../03-risks-and-costs.md#4-vendor-lock-in-map)).
- **Follow-ups:**
  - Budget alerts.
  - Separate `staging` and `prod` projects.
  - Workload Identity Federation for GitHub Actions (no deploy keys).

## When to reconsider
Constant high load, where a committed-use VM or GKE Autopilot becomes
cheaper. That point is far past MVP.
