#!/usr/bin/env bash
# An isolated stack for browser tests, beside the everyday dev servers: its own database
# (recruitai_e2e), API on :8011, scripted worker, and the shared Firebase emulator.
#
#   tests/e2e_stack.sh up      # create the database, start the API and the worker
#   (cd ../web && E2E_WEB_PORT=5174 E2E_API_URL=http://localhost:8011 pnpm exec playwright test radar)
#   tests/e2e_stack.sh down    # stop everything and drop the database
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=.e2e-run
DB=recruitai_e2e
export ENV=local DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/$DB" \
  FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FIREBASE_PROJECT_ID=demo-recruitai \
  APP_CHECK_ENFORCED=false STORAGE_BACKEND=local LOCAL_STORAGE_ROOT=./.data-e2e \
  EMAIL_BACKEND=fake

case "${1:-}" in
up)
  mkdir -p "$RUN"
  docker exec backend-postgres-1 psql -U postgres -q -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB"
  uv run alembic upgrade head > "$RUN/migrate.log" 2>&1
  uv run procrastinate --app=recruitai.worker.app schema --apply >> "$RUN/migrate.log" 2>&1
  nohup uv run uvicorn tests.e2e_server:app --port 8011 > "$RUN/api.log" 2>&1 &
  echo $! > "$RUN/api.pid"
  PYTHONPATH=. nohup uv run procrastinate --app=tests.e2e_worker.app worker > "$RUN/worker.log" 2>&1 &
  echo $! > "$RUN/worker.pid"
  for _ in $(seq 1 30); do curl -sf localhost:8011/health >/dev/null && break; sleep 1; done
  curl -sf localhost:8011/health && echo " api up (:8011), worker started"
  ;;
down)
  for p in api worker; do
    [ -f "$RUN/$p.pid" ] && pkill -P "$(cat "$RUN/$p.pid")" 2>/dev/null; [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null || true
  done
  sleep 1
  docker exec backend-postgres-1 psql -U postgres -q -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)"
  rm -rf "$RUN" .data-e2e
  echo "stack stopped, database dropped"
  ;;
*) echo "usage: $0 up|down"; exit 1 ;;
esac
