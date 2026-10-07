"""A France Travail stand-in with three offers, shared by the e2e API and the e2e worker."""

from recruitai.modules.jobs.schemas import (
    UnifiedJobSearchResponse,
    UnifiedJobSearchResult,
)

OFFERS = {
    "E1": ("Développeur Python Backend", "Fictiva Logiciels"),
    "E2": ("Ingénieur Java Senior", "Corp Industries"),
    "E3": ("Data Engineer Python", "Acme Data"),
}


class Provider:
    name = "france_travail"

    async def search(self, **_: object) -> UnifiedJobSearchResponse:
        return UnifiedJobSearchResponse(
            meta={"count": 3, "page": 1, "total": 3},
            results=[
                UnifiedJobSearchResult(
                    id=i, title=t, company=c, url=f"https://x.test/{i}"
                )
                for i, (t, c) in OFFERS.items()
            ],
        )

    async def detail(self, job_id: str) -> UnifiedJobSearchResult:
        title, company = OFFERS[job_id]
        return UnifiedJobSearchResult(
            id=job_id,
            title=title,
            company=company,
            url=f"https://x.test/{job_id}",
            skills=["Python"],
            contract_type="CDI",
            description=f"{title} chez {company}.",
        )
