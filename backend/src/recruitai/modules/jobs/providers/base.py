"""``JobProvider``: the seam to an external job board (ARCHITECTURE.md §4.4). Async, injected HTTP
client, raises ``AppError`` subclasses only."""

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
