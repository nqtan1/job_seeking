from typing import Dict, List, Optional, Any

from jobs.search.providers.base import BaseJobProvider
from jobs.search.providers.france_travail import FranceTravailProvider
from jobs.search.schema import UnifiedJobSearchResponse
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
        """
        provider = self.get_provider(provider_name)
        self.logger.info(f"Delegating job search to provider '{provider_name}'")
        return provider.search_jobs(
            query=query,
            department=department,
            contract_type=contract_type,
            page=page,
            limit=limit,
        )

    def get_job_detail(self, provider_name: str, job_id: str) -> Dict[str, Any]:
        """
        Routes the fetch detailed job request to the requested provider.
        """
        provider = self.get_provider(provider_name)
        self.logger.info(f"Delegating job detail fetch to provider '{provider_name}'")
        return provider.get_job_detail(job_id)
