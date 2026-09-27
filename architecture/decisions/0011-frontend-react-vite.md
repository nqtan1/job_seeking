# 0011 · React + TypeScript + Vite single-page app

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §5

## Context
Today's frontend is a 1,300-line `index.html` plus about 3,000 lines of
untyped JS. Tailwind is loaded from the CDN (not meant for production), and
the JS files are served by a FastAPI catch-all route. The app is fully behind
a login, has no SEO needs, and has rich interactive screens (split-screen
editor, PDF preview, tracker board).

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **Keep vanilla JS**, add a build step | No rewrite | Manual DOM management doesn't scale to an editor or board; no types; state bugs |
| **HTMX + server templates** | Very little JS; Python-only | Poor fit for rich client interactions (the editor, drag-and-drop tracker, live preview) |
| **Next.js (React)** | SSR/SEO, full-stack | We don't need SSR behind a login; adds a Node server (or Vercel) next to FastAPI; two backends |
| **Vue / Svelte + Vite** | Pleasant, smaller | Smaller ecosystem for the component kits and editors we need; React skills are more transferable and more common in hiring |
| **React + TypeScript + Vite SPA** ✅ | Largest ecosystem (shadcn/ui, TanStack Query, TipTap editor, react-pdf); static build hosted on a CDN; TypeScript catches API misuse | Build tooling to learn; the client bundle must be watched |

**Libraries**

| Need | Choice | Why |
|---|---|---|
| Server state, polling tasks | TanStack Query | Caching, retries, `refetchInterval` for `/tasks/{id}` |
| Routing | React Router | Standard, simple |
| Forms | react-hook-form + zod | Performance and typed validation |
| UI kit | Tailwind v4 (built) + shadcn/ui | You own the component code (no black box); keeps the current Tailwind look |
| Rich text in the letter editor | TipTap | Block-based; maps to the letter blocks |
| PDF preview | react-pdf | Renders the signed-URL PDF |

## Decision
A React 19 + TypeScript (strict) + Vite SPA in `frontend/`, feature folders
under `src/features/`, deployed as static files on Firebase Hosting.

## Why
The product is an interactive tool, not a content site. An SPA on a CDN is
the cheapest, fastest-to-serve option and keeps a single backend (FastAPI).

## Consequences
- **Good:** type-safe end to end (with ADR 0012); components can be reused
  for the future recruiter UI.
- **Bad:** a full rewrite of the UI (phase 3); an initial load cost (keep
  routes lazy-loaded).
- **Follow-ups:**
  - ESLint + Prettier.
  - Vitest + Testing Library.
  - A Playwright smoke test of the main journey.

## When to reconsider
If you add public, SEO-relevant pages (landing, blog, public job pages),
build them as a **separate** static site (Astro, or Next static export). Keep
the app as an SPA.
