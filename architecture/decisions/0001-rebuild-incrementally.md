# 0001 · Rebuild incrementally in place (no big-bang rewrite)

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §7, [02-phases.md](../02-phases.md)

## Context
The current app works as a demo, but its foundations (SQLite on local disk,
in-process queue, env-var API keys, untyped frontend) can't go to production.
About 10k lines of Python (about 40% of it tests) and about 4.3k lines of
frontend JS. The most valuable assets are the **prompts** and the **Pydantic
schemas**. One developer.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **A. Refactor the existing code step by step** | App always runnable; no parallel code | The foundations (DB, queue, auth, frontend) are exactly what's wrong. Refactoring them in place means touching everything anyway, in a less clean order |
| **B. Big-bang rewrite in a new repo** | Clean slate, no legacy constraints | Classic failure mode: months with nothing shippable, then a painful switch-over. Lessons embedded in the old code get lost |
| **C. Build the new skeleton in the same repo, port feature by feature, delete the old code at the end** ✅ | Every phase ends with something working; prompts and schemas are carried over; old code stays as a reference until its replacement is tested | For a while two structures live side by side, which can confuse. Needs discipline to actually do the final delete |

## Decision
Option C. New code lives in `backend/src/recruitai/` and `frontend/src/`.
Features are ported one by one in the order of the v1 user journey. The old
folders are deleted in phase 5.

## Why
The problems are in the **platform** (storage, jobs, auth, contract), not in
the **domain logic** (prompts, schemas). Option C replaces the platform
completely and keeps the domain logic. It also limits risk: if you stop
halfway, you still have a better system than today.

## Consequences
- **Good:** progress is visible, and each phase can be reviewed and tested on
  its own.
- **Bad:** for 1–3 months the repo has two backends. The old one is
  **frozen**: no new features, bug fixes only when blocking.
- **Follow-ups:** a tracking checklist in phase 2 ("old endpoint → new
  endpoint → test → done").

## When to reconsider
If after phase 1 it becomes clear the domain schemas themselves are wrong for
the B2C product, rewrite them as part of phase 2. The strategy stays the same.
