# 0014 · Privacy-first data retention policy

- **Status:** Accepted (product/legal guidance, not legal advice)
- **Related:** ARCHITECTURE.md §11

## Context
CVs are personal data, sometimes with special-category data (health,
religion, photo). Users are in the EU/France, so GDPR applies and the CNIL
(France's privacy regulator) is the reference authority. Today files are kept
forever on local disk, and CV content can end up in log files.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Keep everything forever** | Simplest; "more data for later" | Breaks GDPR storage limitation (Art. 5(1)(e)); a larger breach impact; users increasingly check this |
| **Delete aggressively (e.g. 30 days)** | Minimal risk | Bad UX: a job search lasts months, and users lose their profile and tracker |
| **Keep while the account is active, delete after inactivity, self-service export and delete, short TTLs on temporary data** ✅ | Matches what comparable consumer career tools and CNIL guidance do; good UX; enforceable automatically | Needs scheduled jobs, reminder emails, and export/delete features in v1 |

## Decision
The retention table in ARCHITECTURE.md §11.2:
- Delete after 24 months of inactivity, with warnings.
- Delete drafts after 7 days and caches after 24 h.
- `ai_calls` holds metadata only, kept for 13 months.
- Account deletion is immediate.
- Backups keep data for at most 7 days.

Also:
- Minimization at the schema level (no photo, date of birth, nationality or
  gender fields).
- Vertex AI only for real user data.
- Everything stays in the EU.

## Why
Retention is cheaper to design in than to add later. Enforcing it with
platform features (GCS lifecycle rules, scheduled sweeps) means a code bug
doesn't turn into a compliance failure.

## Consequences
- **Good:**
  - "We don't train AI on your data" and "delete everything in one click"
    are selling points.
  - Smaller breach impact.
- **Bad:**
  - The `privacy` module, export ZIP and sweeps must be built in v1.
  - A transactional email provider is needed for inactivity warnings.
- **Follow-ups:**
  - A privacy policy page.
  - A record of processing activities.
  - Accept the Google Cloud Data Processing Addendum.
  - Have a lawyer or DPO review before public launch.

## When to reconsider
- **Recruiter (B2B) module:** we become a processor for companies. That brings
  a different retention logic (CNIL: at most 2 years after last contact for
  candidates), DPAs with customers, and the EU AI Act high-risk obligations.
  Write a new ADR then.
