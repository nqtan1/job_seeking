# RecruitAI

An AI companion for your job search. Upload your CV once, then let RecruitAI find and score jobs for you, write tailored cover letters, track your applications and coach you through interviews. Your data stays in the EU and is never used to train AI.

## What it does

- **Profile**: your CV is turned into a structured profile (no photo, date of birth or nationality kept).
- **Jobs and radar**: search France Travail, or let the daily radar shortlist matching offers; you approve or dismiss each one.
- **Fit analysis**: strengths, gaps and what is missing for a given job.
- **Letters**: a tailored cover letter you edit block by block, rendered to PDF.
- **Tracker**: applications from saved to offer, with interview reminders.
- **Coach**: a chat grounded in your profile, the job and the fit analysis.
- **Privacy**: export all your data as a ZIP, or delete your account and everything with it, any time.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI API + Procrastinate worker (`src/recruitai/`), Alembic migrations |
| `web/` | React + TypeScript + Vite app |
| `infra/` | Terraform and `deploy.sh` for Google Cloud (Cloud Run, Cloud SQL, Hosting) |
| `.github/workflows/` | CI (checks, tests, images) and CD |

## Run it locally

```bash
cd backend
cp .env.example .env            # ENV=local is required; the app fails fast without it
docker compose up -d            # Postgres 16 + Firebase Auth emulator
uv sync
uv run alembic upgrade head
uv run fastapi dev src/recruitai/main.py                       # API
uv run procrastinate --app=recruitai.worker.app worker          # worker (letters, exports, radar)

cd ../web && pnpm install && pnpm dev                           # web app
```

Checks before a change is done:

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run lint-imports && uv run pytest
cd web && pnpm lint && pnpm typecheck && pnpm test --run && pnpm build
```

Design docs live in `docs/` (gitignored, local only). See `backend/README.md` for backend setup details and `infra/README.md` for deployment.
