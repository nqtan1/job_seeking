from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from domain.jobs.search.schema import UnifiedJobSearchResponse


class BaseJobProvider(ABC):
    """
    Abstract Base Class for all Job Search Providers.
    This architecture is designed to be highly extensible, allowing easy addition
    of platforms like France Travail, LinkedIn, JobTeaser, etc.
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Returns the unique identifier of this provider (e.g. 'france_travail').
        """
        pass

    @abstractmethod
    def search_jobs(
        self,
        query: Optional[str] = None,
        department: Optional[str] = None,
        contract_type: Optional[str] = None,
        page: int = 1,
        limit: int = 25,
    ) -> UnifiedJobSearchResponse:
        """
        Searches job listings and returns a standardized result.

        Returns:
            UnifiedJobSearchResponse: Standard response model.
        """
        pass

    @abstractmethod
    def get_job_detail(self, job_id: str) -> Dict[str, Any]:
        """
        Fetches the full details of a single job.

        Returns:
            Dict: Full job detail, including raw and standardized properties,
                  suitable for conversion to JobPosition schema.
        """
        pass
