from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class UnifiedJobSearchResult(BaseModel):
    """
    Standardized, post-processed job search result across all providers (France Travail, LinkedIn, etc.)
    designed for easy consumption by LLM Agents and frontends.
    """
    id: str = Field(..., description="Unique job listing ID from the provider")
    title: str = Field(..., description="Job position title")
    company: Optional[str] = Field(None, description="Company/Employer name")
    location: Optional[str] = Field(None, description="Job location (city, department, region)")
    date: Optional[str] = Field(None, description="Publication date in YYYY-MM-DD format")
    url: str = Field(..., description="Full original URL to view or apply for the job")
    work_mode: Optional[str] = Field(None, description="Remote, hybrid, or on-site policy")
    regions: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list, description="Key skills extracted from listing")
    description: Optional[str] = Field(None, description="Full or excerpt description")
    contract_type: Optional[str] = Field(None, description="Short code (e.g. CDI, CDD, Freelance)")
    contract_type_label: Optional[str] = Field(None, description="Human-readable contract type name")
    experience_label: Optional[str] = Field(None, description="Required experience description")
    salary_label: Optional[str] = Field(None, description="Human-readable salary statement")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Platform-specific custom metadata attributes")


class UnifiedJobSearchResponse(BaseModel):
    """
    Standardized search response wrapper containing pagination metadata and results list.
    """
    meta: Dict[str, Any] = Field(..., description="Pagination metadata containing count, page, and total results")
    results: List[UnifiedJobSearchResult] = Field(..., description="List of standardized search results")
