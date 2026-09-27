# 0008 · Every user gets a personal organization (`org_id` everywhere)

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §4.4 and §8.1

## Context
v1 serves individuals, but recruiter teams (shared workspaces) are planned.
Adding multi-tenancy **later** to a single-user data model is one of the most
expensive migrations in SaaS: every table, every query, every test.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **`user_id` on every row** (pure B2C) | Simplest now | A later B2B move means re-keying all data and rewriting every query |
| **`org_id` on every row; each user gets a personal org** ✅ | B2C now, B2B later with **no data migration**; one isolation mechanism | Slight overhead now (one extra join or lookup); the concept is invisible to users, but developers must understand it |
| **Schema per tenant** | Strong isolation | Migrations × number of tenants; connection and pool complexity; absurd for thousands of individual users |
| **Database per tenant** | Strongest isolation | Only makes sense for a few large enterprise customers |

## Decision
Shared tables with an `org_id` column (the pool model). At sign-up each user
gets `organizations(kind='personal')` + a `memberships(role='owner')` row.
The UI hides organizations in v1. The later B2B module adds `kind='company'`
orgs and more roles.

## Why
It costs almost nothing now and avoids the most expensive future refactor.
Isolation is enforced at three levels:
1. `OrgContext` comes from the token, never the client.
2. Repositories require `org_id`.
3. Later: Postgres Row-Level Security as a safety net.

## Consequences
- **Good:** the cross-tenant tests written now stay valid forever; B2B is
  additive.
- **Bad:** developers must never forget `org_id` in a query. Mitigated by
  repository signatures plus one cross-tenant test per module.

## When to reconsider
A large enterprise customer contractually requiring physical isolation: offer
them a dedicated DB. The same code works if it's pointed at another database.
