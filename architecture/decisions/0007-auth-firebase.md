# 0007 · Firebase Authentication

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §4.4 and §9

## Context
Today there are no users: tenants are shared API keys in an env variable,
also accepted in the query string. We need real accounts for individuals,
Google sign-in, email verification and password reset. The deployment target
is Google Cloud. One developer: we shouldn't build security-critical auth
flows ourselves.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Self-hosted (fastapi-users, custom JWT)** | No vendor; full control | We own password hashing, reset emails, email verification, OAuth, brute-force protection, token revocation. That's a large, security-critical surface |
| **Keycloak / Zitadel self-hosted** | Full-featured, open source | Another server to run, patch and back up |
| **Auth0 / Clerk** | Excellent developer experience, prebuilt UI (Clerk) | Costs rise quickly with users; outside GCP; one more vendor and data processor |
| **Supabase Auth** | Good, open source | Pulls in another platform when we're on GCP |
| **Firebase Authentication** ✅ | Free tier covers early-stage usage; Google sign-in in a few lines; handles verification and reset emails; **Local Emulator** for dev and tests; upgrade path to **Identity Platform** (MFA, blocking functions, SLA) without code changes; same Google Cloud project and billing | Vendor lock-in for identities (user export is possible); limited customization of email templates; its data model is basic, so roles live in our DB anyway |

## Decision
Firebase Authentication with Google sign-in + email/password (with
verification). The backend verifies ID tokens with `firebase-admin`. **Users,
organizations, memberships and roles live in Postgres**; Firebase only
answers "who is this person".

## Why
Auth is where one developer should buy, not build. Firebase is the cheapest
and simplest option that's native to our cloud, and it has an upgrade path
(Identity Platform) for enterprise needs such as SSO when recruiter accounts
arrive.

## Consequences
- **Good:** no passwords in our system; working auth in about a day;
  emulator-based tests.
- **Bad:**
  - Moving to another provider later means re-verifying users (password
    hashes can be exported with Firebase's tools, but that's a project).
  - Token revocation isn't instant: ID tokens live up to 1 hour unless we
    check revocation on sensitive endpoints.
- **Follow-ups:**
  - Check revocation (`check_revoked=True`) on sensitive endpoints (delete
    account, export).
  - App Check on AI endpoints.
  - Firebase config lives in the frontend env; it isn't secret.

## When to reconsider
B2B customers requiring SAML/OIDC SSO: **upgrade to Identity Platform**
(same SDK). Moving off Google entirely: plan a user migration.
