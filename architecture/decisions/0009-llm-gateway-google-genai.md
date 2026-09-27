# 0009 · Direct `google-genai` SDK behind an `LLMGateway`, no LangChain

- **Status:** Accepted
- **Related:** ARCHITECTURE.md §4.5

## Context
Today every feature has an "agent" class built on LangChain's
`ChatGoogleGenerativeAI`. Each one keeps a `conversation_history` list, even
though almost all calls are single-shot: *document in, structured JSON out*.
The dependencies include `genai` (an unrelated package) and `vertexai`
(deprecated). There's no record of tokens or cost.

## Options considered
| Option | Strengths | Weaknesses |
|---|---|---|
| **LangChain** (keep) | Many integrations; agents and chains | Heavy dependency tree and frequent breaking changes; abstractions hide what's sent to the model; we use about 2% of it; stateful agent objects invite cross-request leaks |
| **LlamaIndex / other frameworks** | Strong for RAG | We don't do RAG in v1 |
| **LiteLLM** (multi-provider proxy) | Switch between OpenAI/Anthropic/Gemini with one API | Another layer; lowest-common-denominator features; we run on one provider for data-residency reasons |
| **Official `google-genai` SDK + thin gateway** ✅ | One official SDK for both the Gemini API and **Vertex AI**; native **structured output** (`response_schema` from Pydantic); native PDF/image input; function calling for the job-search tool loop; we see exactly what's sent | We write about 150 lines of glue ourselves (retries, usage logging); switching provider means writing a second gateway implementation |

## Decision
`ai/gateway.py` defines an `LLMGateway` protocol:
```python
async def generate(*, schema: type[T], system: str, parts: list[Part],
                   feature: str, model: Literal["fast","smart"]="fast") -> T
```
`ai/gemini.py` implements it with `google-genai` (Vertex in prod, API key only
in dev). Calls are stateless. Prompts are versioned modules in
`ai/prompts/` (`PROMPT_VERSION = "cv_extract@3"`).

## Why
Our AI use is **structured extraction and generation**, not autonomous
agents. For that, the official SDK plus Pydantic schemas is the most direct,
debuggable and cheapest path. The gateway keeps business code independent of
the vendor and gives one place for retries, timeouts, cost tracking and
safety.

## Consequences
- **Good:**
  - LangChain and its transitive dependencies are removed.
  - Tests use a `FakeLLMGateway` that returns fixtures, so they're fast and
    free.
  - Each fit report or letter can be traced to `model + prompt_version`.
- **Bad:** we maintain the tool-calling loop for job search ourselves (about
  50 lines).
- **Follow-ups:**
  - An eval set (`tests/evals/`) to run before any prompt or model change.
  - Per-user rate limits and daily quotas stored with `ai_calls`.
  - Prompt-injection hygiene: untrusted text goes inside delimiters, and the
    model gets no write tools.

## When to reconsider
- **We need a second provider** (price, quality, or outage fallback): add
  `ai/anthropic.py` or `ai/openai.py` behind the same protocol, and check data
  residency and processing terms first.
- **Real multi-step agent features** (autonomous job hunting): evaluate an
  agent framework then, for that module only.
