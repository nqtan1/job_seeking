# 0010 · Letters as structured content, rendered with LaTeX via Tectonic

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §10

## Context
Letters are a key B2C feature, and the goal is a writing studio: templates,
paragraph-level edits, versions, several output formats. Today the AI writes
LaTeX directly, and the PDF is compiled with `latexmk`, which **isn't
installed in the Docker image**, so PDF generation silently fails in
containers. A "verbatim LaTeX" co-writing mode exists and is valued.

## Options considered

### Storage model
| Option | Strengths | Weaknesses |
|---|---|---|
| **Raw LaTeX as the stored format** (current) | Maximum typographic control | Can't regenerate one paragraph, switch templates, export to DOCX/email, or run a grounding check without parsing LaTeX. Users must know LaTeX |
| **Structured blocks (JSON)** ✅ + **optional raw LaTeX override** | Templates, per-block AI edits, versions, multi-format export and quality checks all work on clean data; advanced users keep raw mode | Two modes to support; an ejected letter loses template switching |

### Rendering engine
| Option | Strengths | Weaknesses |
|---|---|---|
| **TeX Live + latexmk** | Full LaTeX | Image grows by 1–4 GB; slow cold builds |
| **Tectonic** ✅ | Self-contained LaTeX engine (XeTeX-based); downloads only the packages used (pre-warmed at image build); one binary; keeps LaTeX quality and the existing templates | Package bundle must be cached at build time for offline runtime; fewer packages than a full TeX Live |
| **Typst** | Very fast, simple language, tiny binary | New template language; loses the LaTeX co-writing feature users like |
| **HTML → PDF (WeasyPrint / headless Chromium)** | Web skills reuse; the preview matches the output | Weaker typography for formal letters; Chromium is heavy |
| **DOCX generation (python-docx)** | Recruiters often want Word | Not a PDF engine; we'll add it as an *extra* export, not the primary one |

## Decision
Letters are stored as structured blocks (`content JSONB`) with versions.
PDFs are rendered by Jinja-LaTeX templates compiled by **Tectonic in the
worker only**. `latex_override` allows raw LaTeX editing (eject mode).
DOCX, plain text and email formats come from the same blocks.

## Why
The structured model is what makes the studio features possible. Keeping
LaTeX as the engine protects the existing templates and the co-writing mode
while fixing the Docker problem with a small, container-friendly binary.

## Consequences
- **Good:** templates are data, so adding one is a file. PDF failures happen
  in the worker with retries and are visible to the user.
- **Bad:**
  - LaTeX escaping of user text must be exact: `&`, `%`, `$`, `#`, `_`, `{`,
    `}`, `~`, `^`, `\` all need escaping. One tested helper does it.
  - Tectonic must run with **shell-escape disabled**, a timeout, and a
    memory limit, because raw mode accepts user-written LaTeX.
- **Follow-ups:**
  - An escaping unit test suite.
  - A sandboxing check on raw mode: no `\write18`, no `\input` of absolute
    paths.
  - A preview uses the same pipeline (drafts expire after 7 days).

## When to reconsider
If raw-LaTeX mode is rarely used after launch (measure it) and render time or
image size become a problem, consider Typst for the templated path and keep
LaTeX only for raw mode.
