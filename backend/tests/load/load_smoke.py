"""A small load and abuse check against a running stack (never against prod).

    tests/e2e_stack.sh up
    uv run python tests/load/load_smoke.py --users 50
    tests/e2e_stack.sh down

N users sign up in the Firebase emulator, then all at once: open the app, create a helper and an
automation, run it (queued to the worker) and wait for the result. Then one user hammers the API
and sends an oversize body. Prints p50/p95/max per step and what the limits answered. It exits
non-zero if any step failed or a limit did not trigger.
"""

import argparse
import asyncio
import statistics
import time
import uuid
from collections import defaultdict

import httpx

EMULATOR = (
    "http://localhost:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=x"
)
timings: dict[str, list[float]] = defaultdict(list)
failures: list[str] = []


async def step(name: str, call):
    started = time.perf_counter()
    try:
        r = await call
        if r.status_code >= 400:
            failures.append(f"{name}: HTTP {r.status_code}")
        return r
    except Exception as exc:
        failures.append(f"{name}: {type(exc).__name__}")
        raise
    finally:
        timings[name].append(time.perf_counter() - started)


async def sign_up(c: httpx.AsyncClient) -> dict[str, str]:
    r = await c.post(
        EMULATOR,
        json={
            "email": f"load{uuid.uuid4().hex[:10]}@example.com",
            "password": "password123",
            "returnSecureToken": True,
        },
    )
    return {"Authorization": f"Bearer {r.json()['idToken']}"}


async def one_user(c: httpx.AsyncClient, api: str) -> None:
    h = await sign_up(c)
    await step("open the app (/me)", c.get(f"{api}/me", headers=h))
    await step("list helpers", c.get(f"{api}/agents", headers=h))
    a = (
        await step(
            "create a helper",
            c.post(
                f"{api}/agents",
                headers=h,
                json={
                    "name": "Mira",
                    "spec": {
                        "instructions": "Write a polite follow-up.",
                        "inputs": [
                            {"name": "notes", "label": "Notes", "required": True}
                        ],
                    },
                },
            ),
        )
    ).json()
    i, o, ag = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    graph = {
        "nodes": [
            {"type": "input", "id": i, "fields": [{"name": "n", "label": "n"}]},
            {
                "type": "agent",
                "id": ag,
                "agent_id": a["id"],
                "agent_version_id": a["version_id"],
            },
            {"type": "output", "id": o, "fields": [{"name": "r", "label": "r"}]},
        ],
        "edges": [
            {
                "id": str(uuid.uuid4()),
                "from": {"node": i, "port": "out"},
                "to": ag,
                "map": [{"input": "notes", "value": "{{n}}"}],
            },
            {
                "id": str(uuid.uuid4()),
                "from": {"node": ag, "port": "out"},
                "to": o,
                "map": [{"input": "r", "value": "{{text}}"}],
            },
        ],
    }
    f = (
        await step(
            "create an automation",
            c.post(f"{api}/flows", headers=h, json={"name": "F", "graph": graph}),
        )
    ).json()
    started = time.perf_counter()
    run = (
        await step(
            "start a run",
            c.post(
                f"{api}/flows/{f['id']}/runs", headers=h, json={"inputs": {"n": "hi"}}
            ),
        )
    ).json()
    for _ in range(600):  # up to ~5 minutes
        r = await c.get(f"{api}/flow-runs/{run['id']}", headers=h)
        if r.json().get("status") in ("done", "failed", "cancelled"):
            break
        await asyncio.sleep(0.5)
    timings["run: queued to finished"].append(time.perf_counter() - started)
    if r.json().get("status") != "done":
        failures.append(f"run ended {r.json().get('status')}")
    await step("list runs", c.get(f"{api}/flow-runs", headers=h))


async def abuse(c: httpx.AsyncClient, api: str) -> list[str]:
    h = await sign_up(c)
    await c.get(f"{api}/me", headers=h)
    answers = await asyncio.gather(*(c.get(f"{api}/me", headers=h) for _ in range(450)))
    codes = {r.status_code for r in answers}
    big = await c.post(f"{api}/agents", headers=h, content=b"x" * (13 * 1024 * 1024))
    out = []
    if 429 not in codes:
        out.append("hammering was never slowed (no 429)")
    if big.status_code != 413:
        out.append(f"oversize body answered {big.status_code}, expected 413")
    print(
        f"abuse: 450 quick requests -> {sorted(codes)}; 13 MB body -> {big.status_code}"
    )
    return out


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--api", default="http://127.0.0.1:8011/api/v1")
    args = ap.parse_args()
    async with httpx.AsyncClient(
        timeout=60, limits=httpx.Limits(max_connections=200)
    ) as c:
        t0 = time.perf_counter()
        await asyncio.gather(
            *(one_user(c, args.api) for _ in range(args.users)), return_exceptions=True
        )
        wall = time.perf_counter() - t0
        problems = await abuse(c, args.api)
    print(f"\n{args.users} users at once, {wall:.1f}s wall time\n")
    print(f"{'step':32}{'n':>5}{'p50':>8}{'p95':>8}{'max':>8}")
    for name, xs in timings.items():
        print(
            f"{name:32}{len(xs):>5}{statistics.median(xs):>8.2f}{pct(xs, 0.95):>8.2f}{max(xs):>8.2f}"
        )
    if failures:
        problems.append(f"{len(failures)} failed steps, e.g. {failures[:3]}")
    print("\n" + ("FAILED: " + "; ".join(problems) if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
