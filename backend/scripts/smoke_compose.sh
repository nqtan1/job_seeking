#!/usr/bin/env bash
# Verifies the docker-compose dev stack (P0-04) is up and both services accept
# TCP connections: Postgres (5432) and the Firebase Auth emulator (9099).
set -euo pipefail

check_port() {
    local name="$1" host="$2" port="$3"
    if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
        exec 3<&- 3>&-
        echo "ok: ${name} reachable at ${host}:${port}"
    else
        echo "FAIL: ${name} not reachable at ${host}:${port}" >&2
        exit 1
    fi
}

check_port "postgres" 127.0.0.1 5432
check_port "firebase auth emulator" 127.0.0.1 9099

echo "smoke check passed"
