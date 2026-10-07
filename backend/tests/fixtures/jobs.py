import pytest

from recruitai.core.errors import NotFound
from recruitai.modules.jobs.schemas import (
    UnifiedJobSearchResponse,
    UnifiedJobSearchResult,
)


class FakeJobProvider:
    """Stands in for France Travail: one canned result, ``MISSING`` is a 404."""

    name = "france_travail"

    def __init__(self) -> None:
        self.searches = 0

    async def search(self, **_: object) -> UnifiedJobSearchResponse:
        self.searches += 1
        return UnifiedJobSearchResponse(
            meta={"count": 1, "page": 1, "total": 1},
            results=[
                UnifiedJobSearchResult(id="AB1", title="Dev", url="https://x.test/AB1")
            ],
        )

    async def detail(self, job_id: str) -> UnifiedJobSearchResult:
        if job_id == "MISSING":
            raise NotFound("Job offer not found.")
        return UnifiedJobSearchResult(
            id=job_id,
            title="Dev Python",
            company="Acme",
            url="https://x.test",
            skills=["Python"],
            contract_type="CDI",
            description="Great job",
        )


@pytest.fixture
def fake_job_provider() -> FakeJobProvider:
    return FakeJobProvider()
