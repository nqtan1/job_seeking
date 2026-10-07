"""``JobProvider``: the seam between the jobs service and an external job board (ARCHITECTURE.md
§4.4). Providers are async, take an injected HTTP client, and raise ``AppError`` subclasses
(``UpstreamUnavailable``, ``NotFound``, ``ValidationFailed``), never raw exceptions."""

from typing import Protocol

from recruitai.modules.jobs.schemas import (
    UnifiedJobSearchResponse,
    UnifiedJobSearchResult,
)


class JobProvider(Protocol):
    name: str

    async def search(
        self,
        *,
        query: str | None = None,
        department: str | None = None,
        contract_type: str | None = None,
        page: int = 1,
        limit: int = 25,
    ) -> UnifiedJobSearchResponse: ...

    async def detail(self, job_id: str) -> UnifiedJobSearchResult: ...
