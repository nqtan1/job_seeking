"""France Travail provider (P2-08a): mocked HTTP only, never the real API."""

import httpx
import pytest

from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.modules.jobs.providers.france_travail import (
    FranceTravailProvider,
    normalize_departments,
)

OFFER = {
    "id": "212MZBL",
    "intitule": "Développeur Python",
    "dateCreation": "2026-09-30T08:00:00.000Z",
    "entreprise": {"nom": "Acme"},
    "lieuTravail": {"libelle": "75 - Paris 9e"},
    "typeContrat": "CDI",
    "salaire": {"libelle": "45 000 - 55 000 Euros par an"},
    "competences": [{"libelle": "Python"}, {"code": "x"}],
    "origineOffre": None,
}


def _provider(handler, **kw) -> tuple[FranceTravailProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "entreprise.francetravail.fr":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1499})
        return handler(request)

    async def no_sleep(_: float) -> None:
        return None

    client = httpx.AsyncClient(transport=httpx.MockTransport(route))
    provider = FranceTravailProvider(
        client, client_id="id", client_secret="s", sleep=no_sleep, **kw
    )
    return provider, seen


async def test_search_accepts_206_partial_content_as_a_normal_page():
    # France Travail answers 206 (not 200) when the result set spans several pages.
    provider, _ = _provider(
        lambda r: httpx.Response(
            206,
            json={"resultats": [OFFER]},
            headers={"Content-Range": "offres 0-24/2345"},
        )
    )
    res = await provider.search(query="python")
    assert len(res.results) == 1


async def test_search_maps_results_params_and_total_and_reuses_the_token():
    provider, seen = _provider(
        lambda r: httpx.Response(
            200,
            json={"resultats": [OFFER]},
            headers={"Content-Range": "offres 0-24/2345"},
        )
    )
    first = await provider.search(
        query="python",
        department="Paris, Lyon",
        contract_type="CDD, CDI",
        page=2,
        limit=10,
    )
    await provider.search(query="python")

    job = first.results[0]
    assert (job.id, job.title, job.company, job.date) == (
        "212MZBL", "Développeur Python", "Acme", "2026-09-30",
    )  # fmt: skip
    assert job.skills == ["Python"] and job.url.endswith("/detail/212MZBL")
    assert first.meta == {"count": 1, "page": 2, "total": 2345}
    params = dict(seen[1].url.params)
    assert params["departement"] == "75,69" and params["typeContrat"] == "CDD,CDI"
    assert params["range"] == "10-19" and params["motsCles"] == "python"
    assert sum(r.url.host == "entreprise.francetravail.fr" for r in seen) == 1


async def test_204_is_an_empty_result_and_detail_404_is_not_found():
    provider, _ = _provider(
        lambda r: httpx.Response(204 if "search" in r.url.path else 404)
    )
    assert (await provider.search(query="x")).results == []
    with pytest.raises(NotFound):
        await provider.detail("ABC123")


async def test_5xx_is_retried_then_a_clean_upstream_error():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="secret internal detail")

    provider, _ = _provider(handler)
    with pytest.raises(UpstreamUnavailable) as err:
        await provider.search(query="x")
    assert calls == 4 and "secret" not in str(err.value)  # 1 try + 3 retries

    flaky = iter([httpx.Response(429), httpx.Response(200, json=OFFER)])
    provider, _ = _provider(lambda r: next(flaky))
    assert (await provider.detail("212MZBL")).title == "Développeur Python"


async def test_missing_credentials_and_bad_input_fail_cleanly():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    unconfigured = FranceTravailProvider(client, client_id=None, client_secret=None)
    with pytest.raises(UpstreamUnavailable) as err:
        await unconfigured.search(query="x")
    assert err.value.code == "job_provider_not_configured"

    provider, _ = _provider(lambda r: httpx.Response(200))
    with pytest.raises(ValidationFailed):
        await provider.search(department="Atlantis")
    for bad in ("../admin", "https://x.test/detail/AB1", ""):
        with pytest.raises(ValidationFailed):
            await provider.detail(bad)


@pytest.mark.parametrize(
    ("raw", "codes"),
    [
        ("Paris", "75"),
        ("lyon (69)", "69"),
        ("Hauts-de-Seine, 2a", "92,2A"),
        (None, None),
    ],
)
def test_normalize_departments(raw, codes):
    assert normalize_departments(raw) == codes


async def test_timeouts_and_a_failing_token_endpoint_are_clean_upstream_errors():
    def timing_out(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    provider, _ = _provider(timing_out)
    with pytest.raises(UpstreamUnavailable) as err:
        await provider.search(query="x")
    assert err.value.code == "job_provider_unavailable"

    bad_auth = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad secret"))
    )
    with pytest.raises(UpstreamUnavailable):
        await FranceTravailProvider(bad_auth, client_id="i", client_secret="s").detail(
            "AB1"
        )


@pytest.mark.parametrize(
    "lookalike", ["Saint-Denis", "Marne-la-Vallee", "Sainte-Maxime"]
)
def test_substrings_of_other_words_are_not_departments(lookalike):
    with pytest.raises(ValidationFailed):
        normalize_departments(lookalike)


async def test_a_revoked_token_is_refreshed_once_and_deep_pages_are_rejected():
    tokens = iter(["old", "new"])
    seen_auth: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "entreprise.francetravail.fr":
            return httpx.Response(
                200, json={"access_token": next(tokens), "expires_in": 1499}
            )
        seen_auth.append(request.headers["Authorization"])
        if request.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        return httpx.Response(200, json=OFFER)

    client = httpx.AsyncClient(transport=httpx.MockTransport(route))
    provider = FranceTravailProvider(client, client_id="i", client_secret="s")
    assert (await provider.detail("212MZBL")).id == "212MZBL"
    assert seen_auth == ["Bearer old", "Bearer new"]
    with pytest.raises(ValidationFailed):
        await provider.search(page=100, limit=50)
