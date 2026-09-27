# 0006 · Files in Cloud Storage behind a `Storage` interface

- **Status:** Accepted

## Context
Today uploads and results are written to local folders (`db/cv/uploads/…`,
`/tmp/job_seeking_db/…`), with paths built from user filenames. On Cloud Run
these files vanish. Building paths from user input also invites path
traversal.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Local disk** (keep) | Simple | Ephemeral on Cloud Run; not shared between instances; no lifecycle rules |
| **Postgres `bytea` / large objects** | One system, transactional | Bloats the DB and its backups; expensive storage; slow to stream |
| **Filestore (NFS) / GCS FUSE mount** | Code keeps using file paths | Filestore is expensive; FUSE has surprising semantics (no atomic rename, latency). It hides the real problem |
| **Cloud Storage via SDK** ✅ | Cheap, durable, lifecycle rules (automatic deletion for retention), signed URLs for direct browser downloads, EU region | Network latency per operation; needs a dev substitute |

## Decision
A `Storage` protocol (`put`, `get`, `signed_url`, `delete`, `delete_prefix`)
with two implementations: `GCSStorage` and `LocalStorage` (dev and tests).
Object keys are `orgs/{org_id}/{kind}/{document_id}`, never built from
filenames. Metadata (original filename, MIME, size, sha256) lives in the
`documents` table.

## Why
Storage becomes stateless for containers. **Retention is enforced by the
platform** (lifecycle rules delete drafts after 7 days even if our code has a
bug). Deleting a whole user is `delete_prefix("orgs/{org_id}/")`.

## Consequences
- **Good:** GDPR deletion and export are simple. Downloads don't pass through
  our API (signed URLs).
- **Bad:** there are two stores (DB + GCS), so a DB rollback doesn't undo a
  GCS write. **Rule:** write to GCS first, then commit the DB row. A nightly
  sweep deletes GCS objects that have no matching `documents` row (orphans).
- **Follow-ups:**
  - Bucket with uniform access and no public access.
  - Lifecycle rules for `tmp/`.
  - CORS only if the browser uploads directly (not in v1).

## When to reconsider
Very large files (video) or direct browser uploads. Then add signed *upload*
URLs. The storage choice itself stays.
