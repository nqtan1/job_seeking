#!/usr/bin/env bash
# One group of the backend tests. CI runs each group as its own job (so a red job says which part
# of the system broke), and you can run the same group locally:
#   bash tests/ci_group.sh platform            extra arguments go to pytest: ... platform -x -k flow
# Groups (the last one is "everything not listed", so a new test file is never skipped):
#   unit       tests/unit: pure code, no database, no emulator
#   database   migrations, constraints, transactions, the task queue
#   platform   helpers, flows, blocks, connections
#   accounts   sign-in, tenancy, limits, error shapes, privacy (export, delete, sweeps)
#   product    jobs, letters, coach, matching, radar, tracker, profile, documents, journeys
set -euo pipefail
cd "$(dirname "$0")/.."
shopt -s nullglob
I=tests/integration

database=("$I"/test_migrations.py "$I"/test_db.py "$I"/test_db_failure_modes.py
  "$I"/test_enqueue_atomicity.py "$I"/test_core_tasks.py "$I"/test_ai_quota_concurrency.py
  "$I"/test_documents_ai_calls_constraints.py "$I"/test_identity_constraints.py)
platform=("$I"/test_agents.py "$I"/test_flow*.py "$I"/test_engine*.py "$I"/test_connections*.py)
accounts=("$I"/test_auth.py "$I"/test_tenancy.py "$I"/test_identity_me.py "$I"/test_admin_users.py
  "$I"/test_abuse_limits.py "$I"/test_app_resilience.py "$I"/test_error_responses.py
  "$I"/test_request_logging.py "$I"/test_reminders.py "$I"/test_privacy_*.py)

group="${1:?usage: ci_group.sh unit|database|platform|accounts|product [pytest args]}"
shift
case "$group" in
  unit) exec uv run pytest tests/unit "$@" ;;
  database) exec uv run pytest "${database[@]}" "$@" ;;
  platform) exec uv run pytest "${platform[@]}" "$@" ;;
  accounts) exec uv run pytest "${accounts[@]}" "$@" ;;
  product)
    skip=(--ignore=tests/unit)
    for f in "${database[@]}" "${platform[@]}" "${accounts[@]}"; do skip+=(--ignore="$f"); done
    exec uv run pytest tests "${skip[@]}" "$@" ;;
  *) echo "unknown group: $group" >&2; exit 2 ;;
esac
