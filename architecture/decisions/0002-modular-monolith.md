# 0002 · Modular monolith, not microservices

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §4.1

## Context
One developer, one product, early stage, unknown traffic. The current code is
split by technical layer (`api/`, `application/`, `domain/`,
`infrastructure/`) into more than 60 small folders, so one feature is spread
over 4–5 places.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Layered monolith** (current style) | Familiar "clean architecture" look | A feature is scattered across the tree. Nothing stops feature A reaching into feature B's tables. Many almost-empty folders |
| **Microservices** (one service per feature) | Independent deploys and scaling; team autonomy | Needs network calls, distributed transactions, per-service CI/CD, tracing, versioning. That's a large operations cost with no benefit for a team of one |
| **Modular monolith** ✅ | One deployable, one DB, one CI. Each feature lives in one folder. Module boundaries are enforced by `import-linter` | One DB means a bad migration affects everything. Modules can't scale separately (the API/worker split covers the only real need) |

## Decision
One codebase, one database, two process types (API, worker). The code is
organized in `modules/<feature>/`, each with `router / service / repository
/ models / schemas / tasks`. Cross-module access goes only through
`service.py`.

## Why
Microservices solve **organizational** scaling (many teams), not technical
scaling. A modular monolith gives the same **code** separation at a fraction
of the operations cost. If a module ever needs to become a service (for
example, PDF rendering), a clean module boundary makes that extraction a
mechanical job.

## Consequences
- **Good:** a local transaction can span modules when needed. Simple
  debugging, single deploy.
- **Bad:** boundaries rely on lint rules and review, not on the network.
  Discipline is required.
- **Follow-ups:** an `import-linter` contract in CI (`modules.* may not import
  modules.*.repository`).

## When to reconsider
More than about 3 teams working on the codebase, or one module with radically
different scaling or availability needs (for example, a real-time feature).
