## What and why

<!-- One concern per PR. Link the task id (e.g. M1, S12). -->

## Checklist (handbook §8; a "no" is a request for changes)

- [ ] Right module; other modules only through `service.py`; router has HTTP only; service has no FastAPI
- [ ] Every query filters by `org_id`; cross-tenant test for new endpoints
- [ ] Schema change by an Alembic migration (expand/contract); relations loaded with `selectinload`
- [ ] Slow or retryable work is a task; AI calls go through `LLMGateway` with a feature and a versioned prompt
- [ ] Evals ran if a prompt or model changed
- [ ] Nothing personal logged or sent to a third party; blocking code runs in a thread
- [ ] `response_model` declared and `pnpm gen:api` run
- [ ] Tests for the happy path and the main failure path
- [ ] New setting in `config*.yaml` / `.env.example` and in `infra/` (deploy-env-parity)
