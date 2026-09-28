# RecruitAI backend

Design docs live in `docs/` at the repo root (gitignored, local-only — ask
whoever set up your checkout for a copy if it's missing).

## Setup

```bash
cp .env.example .env   # then fill in the secrets you need; ENV=local is required
uv sync
docker compose up -d   # Postgres 16 + Firebase Auth emulator
uv run fastapi dev src/recruitai/main.py
```

`Settings` (`src/recruitai/config.py`) fails fast if `ENV` isn't set — that's
by design, not a bug: copy `.env.example` to `.env` first.
