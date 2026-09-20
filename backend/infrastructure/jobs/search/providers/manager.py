from typing import Dict, List, Optional, Any

from infrastructure.jobs.search.providers.base import BaseJobProvider
from infrastructure.jobs.search.providers.france_travail import FranceTravailProvider
from domain.jobs.search.schema import UnifiedJobSearchResponse
from infrastructure.jobs.search.cache import JobCacheManager
from utils.logger import get_logger


class JobProviderManager:
    """
    Manager class responsible for orchestrating multiple Job Search Providers.
    It registers platforms (e.g. France Travail) and routes search / details
    requests to the appropriate provider, allowing easy system extension.
    """

    def __init__(self, logger_name: str = "jobs.providers.manager"):
        self.logger = get_logger(name=logger_name, log_file="jobs_api.log", level="INFO")
        self._providers: Dict[str, BaseJobProvider] = {}
        self.cache_manager = JobCacheManager()
        
        # Auto-register core providers
        self.register_provider(FranceTravailProvider())
        
        # Future providers like LinkedIn and JobTeaser can be registered here as stubs or placeholders
        # self._providers["linkedin"] = LinkedInProvider() # stub
        # self._providers["jobteaser"] = JobTeaserProvider() # stub

    def register_provider(self, provider: BaseJobProvider) -> None:
        name = provider.get_provider_name()
        self._providers[name] = provider
        self.logger.info(f"Registered job search provider: '{name}'")

    def get_provider(self, name: str) -> BaseJobProvider:
        if name not in self._providers:
            self.logger.error(f"Provider '{name}' is not registered.")
            raise ValueError(f"Provider '{name}' is not registered/supported.")
        return self._providers[name]

    def list_providers(self) -> List[str]:
        """
        Returns a list of all registered provider names.
        """
        return list(self._providers.keys())

    def search_jobs(
        self,
        provider_name: str,
        query: Optional[str] = None,
        department: Optional[str] = None,
        contract_type: Optional[str] = None,
        page: int = 1,
        limit: int = 25,
    ) -> UnifiedJobSearchResponse:
        """
        Routes the search request to the requested provider.
        Utilizes caching to avoid redundant provider hits.
        """
        # 1. Check cache first
        cached_result = self.cache_manager.get_cached_search(
            provider=provider_name,
            query=query,
            dept=department,
            contract=contract_type,
            page=page,
            limit=limit,
        )
        if cached_result is not None:
            self.logger.debug(f"Cache hit for search_jobs: provider={provider_name}, query={query}")
            return cached_result

        # 2. Fetch from real provider on cache miss
        provider = self.get_provider(provider_name)
        self.logger.info(f"Delegating job search to provider '{provider_name}'")
        response = provider.search_jobs(
            query=query,
            department=department,
            contract_type=contract_type,
            page=page,
            limit=limit,
        )

        # 3. Save to cache
        self.cache_manager.save_cached_search(
            provider=provider_name,
            query=query,
            dept=department,
            contract=contract_type,
            page=page,
            limit=limit,
            response=response,
        )
        return response

    def get_job_detail(self, provider_name: str, job_id: str) -> Dict[str, Any]:
        """
        Routes the fetch detailed job request to the requested provider.
        Utilizes caching to avoid redundant provider hits.
        """
        # 1. Check cache first
        cached_detail = self.cache_manager.get_cached_detail(provider=provider_name, job_id=job_id)
        if cached_detail is not None:
            self.logger.debug(f"Cache hit for get_job_detail: provider={provider_name}, job_id={job_id}")
            return cached_detail

        # 2. Fetch from real provider on cache miss
        provider = self.get_provider(provider_name)
        self.logger.info(f"Delegating job detail fetch to provider '{provider_name}'")
        detail_data = provider.get_job_detail(job_id)

        # 3. Save to cache
        self.cache_manager.save_cached_detail(
            provider=provider_name,
            job_id=job_id,
            detail_data=detail_data,
        )
        return detail_data
