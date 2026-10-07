"""The one France Travail provider per process (it keeps the OAuth token in memory), shared by
the jobs router and the worker's radar task."""

from functools import lru_cache

import httpx

from recruitai.config import get_settings
from recruitai.modules.jobs.providers.france_travail import FranceTravailProvider


@lru_cache
def france_travail_provider() -> FranceTravailProvider:
    s = get_settings()
    return FranceTravailProvider(
        httpx.AsyncClient(),
        client_id=s.france_travail_client_id,
        client_secret=s.france_travail_client_secret,
        base_url=s.france_travail_api_url,
    )
