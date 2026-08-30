# Job Seeking System Design

## Current State

The current backend already covers the core idea:

- CV upload and extraction
- Job description upload/raw-text extraction
- Candidate analysis and recruiter analysis schemas
- Motivation letter generation
- Gemini provider support through either API key or Vertex AI

What is still weak for a real multi-client product:

- Routes create global agent instances at import time.
- `BaseAgent` keeps in-memory conversation history, which is unsafe for shared request handling if chat-style features grow.
- Storage is file-folder based only, so there is no tenant, user, or project isolation.
- The `fit` module is not fully wired yet.
- There is no queue, no auth layer, no billing/tenant boundary, and no UI-facing API contract.

## Recommended Target Architecture

For about 20 clients, the right target is a small multi-tenant system, not a single shared singleton app.

### 1. API Layer

Keep FastAPI, but make routers thin. They should only:

- validate input
- resolve the current tenant/user context
- call an application service
- return a response model

Recommended route groups:

- `/api/v1/cv`
- `/api/v1/jobs`
- `/api/v1/fit`
- `/api/v1/letters`
- `/api/v1/hr`
- `/api/v1/projects`
- `/api/v1/health`

### 2. Application Services

Move orchestration out of route files into services/use cases.

Examples:

- `CVService.extract_cv()`
- `JobService.extract_job()`
- `FitService.score_candidate()`
- `LetterService.generate_letter()`
- `HRService.rank_candidates()`
- `NotificationService.send_rejection_email()`

These services should be stateless and receive all request context explicitly.

### 3. Agent Layer

Treat agents as providers, not application state.

Recommended agent pattern:

- `CVExtractionAgent`
- `JobExtractionAgent`
- `FitAnalysisAgent`
- `MotivationLetterAgent`

Each agent should:

- create a model client per service instance or per request scope
- avoid sharing conversation history across users
- expose one task-oriented method per action
- return typed schemas only

### 4. Domain Layer

Keep your current idea, but make the domain explicit:

- CV extraction
- Job extraction
- Fit analysis
- Letter generation
- HR candidate ranking
- Interview context simulation

Suggested domain entities:

- `Tenant`
- `User`
- `Project`
- `CVDocument`
- `JobDocument`
- `CandidateProfile`
- `JobProfile`
- `FitAssessment`
- `LetterDraft`
- `InterviewSimulation`
- `HRSelectionRun`

### 5. Persistence Layer

Replace the ad hoc `db/*/uploads|extract|analyze` folder strategy with a tenant-aware storage scheme.

Suggested storage split:

- Database: metadata, tenant ownership, analysis status, scores, audit logs
- Object storage: uploaded files, generated JSON, generated letters, exports

Suggested object path pattern:

- `tenants/{tenant_id}/projects/{project_id}/cv/{doc_id}/original.pdf`
- `tenants/{tenant_id}/projects/{project_id}/jobs/{doc_id}/original.pdf`
- `tenants/{tenant_id}/projects/{project_id}/outputs/{run_id}/fit.json`
- `tenants/{tenant_id}/projects/{project_id}/outputs/{run_id}/letter.txt`

For 20 clients, this is enough. You do not need distributed storage complexity yet.

### 6. Async Jobs

Anything involving file uploads, OCR, LLM calls, ranking, or email should be runnable asynchronously.

Use a queue worker for:

- CV extraction
- Job extraction
- Fit analysis
- Letter generation
- HR batch candidate ranking
- Email sending

Recommended stack:

- Redis + RQ or Celery
- PostgreSQL for job status and audit trail

### 7. Multi-Tenant Control

This is the main thing needed for 20 clients.

Every request should carry:

- `tenant_id`
- `project_id`
- `user_id`
- `role` or permission scope

Enforce isolation at every layer:

- API auth
- database queries
- storage paths
- logs and audit events
- rate limits

### 8. Frontend / No-Code Direction

Your UI should not expose agent internals.

Recommended product flows:

- Employee mode
  - upload CV
  - paste or upload job description
  - get fit score
  - get improved CV bullets / cover letter draft
  - get interview simulation prompts

- HR mode
  - upload JD
  - upload many CVs
  - compare candidates
  - apply custom ranking criteria
  - export shortlist
  - draft reject/continue email

For no-code friendliness, design the frontend as a guided wizard, not as raw forms.

## Better Request Flow

### Employee Flow

1. User logs in and selects a project.
2. CV is uploaded and extracted.
3. Job is added manually or from a file.
4. Fit service scores the match.
5. Letter service generates a tailored letter.
6. Interview service generates likely questions, context, and weak spots.

### HR Flow

1. HR user creates a job requisition.
2. Candidates are uploaded or imported.
3. Fit/ranking service scores all candidates against the JD and custom conditions.
4. HR reviews shortlist and reasons.
5. Optional email workflow sends reject/next-step messages.

## What I Would Restructure First

If you want the smallest useful refactor, do this order:

1. Make route handlers thin and move orchestration into services.
2. Remove global agent instances from route modules.
3. Make agents stateless per request or per service call.
4. Add tenant/project models and metadata storage.
5. Wire the `fit` module into the same service pattern.
6. Add background jobs for heavy operations.
7. Add a frontend wizard over the API.

## Suggested Code Layout

```text
app/
  api/
    v1/
      cv.py
      jobs.py
      fit.py
      letters.py
      hr.py
  core/
    config.py
    security.py
    logging.py
  domain/
    cv/
    jobs/
    fit/
    letters/
    hr/
  services/
    cv_service.py
    job_service.py
    fit_service.py
    letter_service.py
    hr_service.py
  agents/
    cv_agent.py
    job_agent.py
    fit_agent.py
    letter_agent.py
  repositories/
  workers/
  schemas/
  ui/
```

## Practical Scaling Notes for 20 Clients

- Use one shared backend, not one deployment per client.
- Keep one tenant-aware database.
- Use per-tenant storage prefixes.
- Put LLM calls behind queue workers for burst protection.
- Add rate limits per tenant to protect API and model quotas.
- Add audit logs for every generated artifact.
- Add retry and idempotency for uploads and generation jobs.

## Bottom Line

Your current idea is solid. The missing piece is not more AI features first; it is product structure:

- explicit tenant/project ownership
- stateless services
- asynchronous processing
- a thin API layer
- a guided UI on top

That gives you a product that can support roughly 20 clients cleanly without overengineering.