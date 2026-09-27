# 0005 · Postgres-backed task queue (Procrastinate)

- **Status:** Accepted, with a named fallback (Cloud Tasks)
- **Related:** ARCHITECTURE.md §4.6, walkthrough §5

## Context
Some work is slow (PDF compile, data export), fails for reasons outside our
control (Gemini 429s, France Travail downtime), or runs on a schedule
(retention sweeps). Today a polling thread inside the API process runs it,
using SQLite. That design loses jobs on restart and breaks with more than one
instance.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Keep custom SQLite poller** | Already written | Not durable on Cloud Run, not multi-instance, competes with the API for CPU, and we'd maintain a queue ourselves |
| **Celery + Redis** | The industry standard; huge ecosystem | Adds Redis (Memorystore has a fixed monthly cost); Celery is complex to configure and is sync-first; enqueueing isn't transactional with our DB |
| **ARQ / Dramatiq / Taskiq + Redis** | Lighter than Celery, some async-native | Still needs Redis; smaller communities |
| **Google Cloud Tasks → HTTP endpoint on Cloud Run** | Fully managed; **scales to zero** (no always-on worker); built-in retries and rate limits | Enqueue isn't transactional with Postgres (possible orphan state); GCP lock-in; local dev needs an emulator or bypass; each task is an HTTP request with a timeout |
| **Pub/Sub push** | Managed, massive scale | Built for events, not jobs; the same transactional gap; overkill |
| **Procrastinate (Postgres)** ✅ | **Uses the DB we already have**; enqueue **in the same transaction** as business writes; async-native; retries, locks, periodic tasks; works identically locally | Smaller community than Celery. Throughput is limited by Postgres (fine up to thousands of jobs/min). Needs an **always-running worker process** |

## Decision
Procrastinate, with a separate worker process. All enqueueing goes through
`core/tasks.py`, so feature code never imports Procrastinate directly. That
makes a later switch cheap.

## Why
- **Correctness first:** for us the most important property is that "row
  updated" and "job enqueued" are atomic. Only a queue inside our DB gives
  that without extra patterns (outbox).
- **Operational simplicity:** zero new infrastructure; the same backups; the
  same local setup (`docker compose up` gives you everything).

## Consequences
- **Good:** no lost jobs, no orphan states, easy local debugging (the jobs are
  just rows).
- **Bad:** the worker must be always on. On Cloud Run that means min
  instances = 1 with CPU always allocated (or Cloud Run worker pools), which
  is a small fixed monthly cost. Every worker also holds a DB connection.
- **Follow-ups:**
  - A `/tasks/{id}` endpoint that reads the domain status, not queue internals.
  - An alert when the number of failed jobs per hour exceeds N.

## When to reconsider
- **The fixed worker cost is too high for early-stage traffic:** switch to
  **Cloud Tasks** (scale to zero). Keep the same `core/tasks.py` interface and
  add an outbox table to regain atomicity.
- **Throughput above about 50 jobs/second sustained:** move to Redis-based or
  managed queues.
