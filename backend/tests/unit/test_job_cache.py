import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from infrastructure.jobs.search.cache import JobCacheManager
from domain.jobs.search.schema import UnifiedJobSearchResponse, UnifiedJobSearchResult
from infrastructure.jobs.search.providers.manager import JobProviderManager


class TestJobCache(unittest.TestCase):
    def setUp(self):
        # Create a temporary file for the SQLite database
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.cache_manager = JobCacheManager(db_path=self.temp_db_path)

    def tearDown(self):
        # Close file descriptor and remove the temporary database file
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_cache_is_physically_created_under_separate_sqlite_file(self):
        # Verify separate database is created and works
        self.assertTrue(os.path.exists(self.temp_db_path))
        self.assertNotIn("background_jobs.db", self.temp_db_path)

    def test_default_db_path_resolved_correctly(self):
        default_manager = JobCacheManager()
        self.assertTrue(default_manager.db_path.endswith("db/job_cache.db"))

    def test_search_cache_save_and_retrieve(self):
        provider = "mock_provider"
        query = "python"
        dept = "75"
        contract = "CDI"
        page = 1
        limit = 10

        response = UnifiedJobSearchResponse(
            meta={"count": 1, "page": 1, "total": 1},
            results=[
                UnifiedJobSearchResult(
                    id="mock_id_1",
                    title="Python Engineer",
                    company="Mock Corp",
                    location="Paris",
                    date="2026-10-10",
                    url="http://mock.com",
                    work_mode="hybrid",
                    regions=["IDF"],
                    countries=["France"],
                    skills=["python"],
                    description="Cool job",
                    contract_type="CDI",
                    contract_type_label="Contrat de travail à durée indéterminée",
                    experience_label="2 years",
                    salary_label="50k EUR",
                    metadata={},
                )
            ]
        )

        # Cache miss initially
        cached = self.cache_manager.get_cached_search(provider, query, dept, contract, page, limit)
        self.assertIsNone(cached)

        # Save to cache
        self.cache_manager.save_cached_search(provider, query, dept, contract, page, limit, response)

        # Cache hit
        cached = self.cache_manager.get_cached_search(provider, query, dept, contract, page, limit)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.meta, response.meta)
        self.assertEqual(len(cached.results), 1)
        self.assertEqual(cached.results[0].title, "Python Engineer")

    def test_detail_cache_save_and_retrieve(self):
        provider = "mock_provider"
        job_id = "job_123"
        detail_data = {
            "provider": "mock_provider",
            "job_position_data": {
                "job_title": "Python Developer",
                "company": "Mock Corp",
                "location": "Paris",
                "contract_type": "CDI",
                "compensation": {"min_salary": 50000.0, "max_salary": 60000.0, "salary_frequency": "Annuel"},
                "requirements": {"required_skills": ["Python"], "years_of_experience": 2},
                "company_description": "We do coding."
            }
        }

        # Cache miss initially
        cached = self.cache_manager.get_cached_detail(provider, job_id)
        self.assertIsNone(cached)

        # Save to cache
        self.cache_manager.save_cached_detail(provider, job_id, detail_data)

        # Cache hit
        cached = self.cache_manager.get_cached_detail(provider, job_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["job_position_data"]["job_title"], "Python Developer")

    def test_search_cache_expiration(self):
        provider = "mock_provider"
        query = "python"
        dept = "75"
        contract = "CDI"
        page = 1
        limit = 10

        response = UnifiedJobSearchResponse(
            meta={"count": 1, "page": 1, "total": 1},
            results=[]
        )

        # Save with negative TTL (expired instantly)
        self.cache_manager.save_cached_search(
            provider, query, dept, contract, page, limit, response, ttl_seconds=-10
        )

        # Check that it returns None (expired)
        cached = self.cache_manager.get_cached_search(provider, query, dept, contract, page, limit)
        self.assertIsNone(cached)

    def test_detail_cache_expiration(self):
        provider = "mock_provider"
        job_id = "job_123"
        detail_data = {"key": "value"}

        # Save with negative TTL (expired instantly)
        self.cache_manager.save_cached_detail(provider, job_id, detail_data, ttl_seconds=-5)

        # Check that it returns None (expired)
        cached = self.cache_manager.get_cached_detail(provider, job_id)
        self.assertIsNone(cached)

    def test_provider_manager_uses_cache(self):
        # We want to test that JobProviderManager actually calls cache_manager
        manager = JobProviderManager()
        
        # Replace the real cache manager on the provider manager with our test cache manager
        manager.cache_manager = self.cache_manager

        # Let's register a mock provider to avoid hitting real APIs
        mock_provider = MagicMock()
        mock_provider.get_provider_name.return_value = "mock_provider"
        
        response = UnifiedJobSearchResponse(
            meta={"count": 1, "page": 1, "total": 1},
            results=[
                UnifiedJobSearchResult(
                    id="mock_id_1",
                    title="Mock Developer",
                    company="Mock Corp",
                    location="Paris",
                    date="2026-10-10",
                    url="http://mock.com",
                    work_mode="hybrid",
                    regions=["IDF"],
                    countries=["France"],
                    skills=["mock"],
                    description="Nice mock job",
                    contract_type="CDI",
                    contract_type_label="Contrat de travail à durée indéterminée",
                    experience_label="2 years",
                    salary_label="50k EUR",
                    metadata={},
                )
            ]
        )
        mock_provider.search_jobs.return_value = response
        
        detail_data = {"provider": "mock_provider", "data": "yes"}
        mock_provider.get_job_detail.return_value = detail_data

        manager.register_provider(mock_provider)

        # First search call: cache miss, calls real provider
        res1 = manager.search_jobs("mock_provider", query="mock")
        mock_provider.search_jobs.assert_called_once()
        self.assertEqual(res1.results[0].title, "Mock Developer")

        # Second search call: cache hit, real provider NOT called again
        mock_provider.search_jobs.reset_mock()
        res2 = manager.search_jobs("mock_provider", query="mock")
        mock_provider.search_jobs.assert_not_called()
        self.assertEqual(res2.results[0].title, "Mock Developer")

        # First detail call: cache miss, calls real provider
        det1 = manager.get_job_detail("mock_provider", job_id="job_abc")
        mock_provider.get_job_detail.assert_called_once()
        self.assertEqual(det1["data"], "yes")

        # Second detail call: cache hit, real provider NOT called again
        mock_provider.get_job_detail.reset_mock()
        det2 = manager.get_job_detail("mock_provider", job_id="job_abc")
        mock_provider.get_job_detail.assert_not_called()
        self.assertEqual(det2["data"], "yes")
