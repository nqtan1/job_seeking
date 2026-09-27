# 0004 · PostgreSQL + SQLAlchemy 2.0 (async) + Alembic

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §4.3, ADR 0005, ADR 0013

## Context
Today there are two SQLite files on the container's local disk, JSON stored
as TEXT, no foreign keys, and a hand-written migration runner. On Cloud Run,
local disk is **ephemeral and per instance**: data disappears on restart and
isn't shared between instances.

## Options considered

### Database
| Option | Strengths | Weaknesses |
|---|---|---|
| **SQLite** (keep) | Zero ops, fast | Single-writer, single machine; unusable on Cloud Run without hacks (Litestream, a volume) |
| **PostgreSQL (Cloud SQL)** ✅ | Relational integrity (FKs, constraints), **JSONB** for AI outputs, full-text search, row-level security, hosts the task queue too; standard skill, portable to any cloud | Fixed monthly cost (smallest instance still costs money); connections are limited, so a pool is needed |
| **Firestore** (Google NoSQL) | Serverless, free tier, integrates with Firebase | No joins or transactions across collections in the relational sense; tenant isolation by rules, not SQL; hard to query for analytics; strong lock-in |
| **MongoDB Atlas** | Flexible documents | Our data **is** relational (user → profile → jobs → fits → letters → applications). Another vendor outside GCP |
| **AlloyDB** | Postgres-compatible, faster | Far more expensive; overkill before real scale |

### Data access layer
| Option | Strengths | Weaknesses |
|---|---|---|
| **SQLAlchemy 2.0** ✅ | The standard Python ORM; typed `Mapped[]` models; async support; Alembic autogenerate | Learning curve; easy to write N+1 queries if careless |
| **SQLModel** | Pydantic + SQLAlchemy in one class | Mixing API schemas with DB tables couples them. Smaller community, lags SQLAlchemy features |
| **Raw SQL (asyncpg)** | Full control, fastest | Hand-written mapping, migrations and query building. More code, more bugs |

## Decision
Cloud SQL for PostgreSQL 16. SQLAlchemy 2.0 async with the `asyncpg` driver.
Alembic for migrations. AI outputs are stored as **JSONB** plus a few
extracted columns we filter on (score, title, company). Every tenant table
has `org_id` + FK + an index.

## Why
Postgres is the "boring" choice that covers 100% of our needs: relational
data, semi-structured AI output (JSONB), the task queue (ADR 0005), and later
full-text search and RLS. That means **one stateful system to operate**
instead of three. It's also the most portable choice (any cloud, Supabase,
Neon, or self-hosted) and reduces lock-in.

## Consequences
- **Good:** FKs make orphan data impossible. JSONB lets the CV schema evolve
  without migrations. `pg_dump` gives a portable backup.
- **Bad:** about 10–30 €/month minimum for the smallest instance (see
  [03-risks-and-costs](../03-risks-and-costs.md)). Connection limits mean the
  pool size × number of instances must stay below the instance's limit.
- **Follow-ups:**
  - Configure pool size per process.
  - Use the Cloud SQL Python Connector or the Auth Proxy (IAM auth, no
    passwords).
  - Test restoring from backup once before launch.

## When to reconsider
- **DB cost matters too much at zero users:** use Neon/Supabase free tier
  Postgres for staging only. It's the same code.
- **Read load becomes a bottleneck:** add a read replica. This is far away
  for a B2C MVP.
