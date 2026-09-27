import unittest
from unittest.mock import MagicMock, patch
import os
import json
import time

from infrastructure.jobs.providers.france_travail import FranceTravailProvider
from infrastructure.jobs.providers.manager import JobProviderManager


class TestJobProviders(unittest.TestCase):
    def setUp(self):
        # Patch credentials check so we don't throw validation error
        self.env_patcher = patch.dict("os.environ", {
            "FRANCE_TRAVAIL_CLIENT_ID": "test_client_id",
            "FRANCE_TRAVAIL_CLIENT_SECRET": "test_client_secret"
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("infrastructure.jobs.search.providers.france_travail.requests.post")
    def test_france_travail_token_cache(self, mock_post):
        # Mock oauth token response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "mock_token_12345",
            "expires_in": 3600
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        provider = FranceTravailProvider()
        
        # Mock Path.exists and read_text / write_text to prevent actual file writes
        with patch("infrastructure.jobs.search.providers.france_travail.Path.exists", return_value=False), \
             patch("infrastructure.jobs.search.providers.france_travail.Path.write_text") as mock_write:
            token = provider._get_token()
            self.assertEqual(token, "mock_token_12345")
            mock_post.assert_called_once()
            mock_write.assert_called_once()

    @patch("infrastructure.jobs.search.providers.france_travail.FranceTravailProvider._api_get")
    def test_france_travail_search(self, mock_api_get):
        provider = FranceTravailProvider()
        
        # Mock search response
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.headers = {"Content-Range": "offres 0-1/2"}
        
        mock_data = {
            "resultats": [
                {
                    "id": "123XYZ",
                    "intitule": "Python Developer",
                    "entreprise": {"nom": "Awesome Startup"},
                    "lieuTravail": {"libelle": "Paris 75"},
                    "dateCreation": "2026-09-01T10:00:00.000Z",
                    "description": "Develop nice backend features",
                    "typeContrat": "CDI",
                }
            ]
        }
        mock_api_get.return_value = (mock_res, mock_data)

        results = provider.search_jobs(query="python", department="75")
        
        self.assertEqual(results.meta["total"], 2)
        self.assertEqual(results.meta["count"], 1)
        self.assertEqual(results.results[0].id, "123XYZ")
        self.assertEqual(results.results[0].title, "Python Developer")
        self.assertEqual(results.results[0].company, "Awesome Startup")

    def test_france_travail_normalization(self):
        provider = FranceTravailProvider()
        
        # Test numeric pass-through
        self.assertEqual(provider._normalize_department("75"), "75")
        self.assertEqual(provider._normalize_department("75,69"), "75,69")
        self.assertEqual(provider._normalize_department("75, 69"), "75,69")
        
        # Test exact city lookup
        self.assertEqual(provider._normalize_department("Paris"), "75")
        self.assertEqual(provider._normalize_department("lyon"), "69")
        
        # Test accent stripping
        self.assertEqual(provider._normalize_department("Bouches-du-Rhône"), "13")
        self.assertEqual(provider._normalize_department("Côte-d'Or"), "21")
        
        # Test partial containing
        self.assertEqual(provider._normalize_department("Marseille (13000)"), "13")
        self.assertEqual(provider._normalize_department("Paris 13ème"), "75")
        
        # Test multi-city split lists
        self.assertEqual(provider._normalize_department("Paris, Lyon"), "75,69")
        
        # Test strict error raising for unrecognized locations or typos to aid developer debugging
        with self.assertRaises(ValueError):
            provider._normalize_department("Pairs")
            
        with self.assertRaises(ValueError):
            provider._normalize_department("UnknownPlace")
            
        with self.assertRaises(ValueError):
            provider._normalize_department("Paris, UnknownPlace")
            
        self.assertIsNone(provider._normalize_department(None))

    @patch("infrastructure.jobs.search.providers.france_travail.FranceTravailProvider._api_get")
    def test_france_travail_detail_and_mapping(self, mock_api_get):
        provider = FranceTravailProvider()
        
        # Mock single job detail response
        mock_res = MagicMock()
        mock_res.status_code = 200
        
        mock_job_detail = {
            "id": "999ABC",
            "intitule": "Chef de projet IA",
            "description": "Super high level project management with Python and Machine Learning, 5 ans d'experience requested.",
            "dateCreation": "2026-09-05T08:00:00.000Z",
            "lieuTravail": {"libelle": "Marseille (13)"},
            "typeContrat": "CDD",
            "typeContratLibelle": "Contrat à durée déterminée",
            "experienceExige": "5 ans d'experience",
            "experienceLibelle": "5 ans",
            "salaire": {
                "libelle": "45 000,00 - 55 000,00 EUR par an",
                "commentaire": "Prime de Noel"
            },
            "entreprise": {
                "nom": "AI Lab",
                "description": "We build deep learning models."
            },
            "competences": [
                {"libelle": "Project Management"},
                {"libelle": "Python"}
            ]
        }
        mock_api_get.return_value = (mock_res, mock_job_detail)

        detail_result = provider.get_job_detail("999ABC")
        
        self.assertEqual(detail_result["provider"], "france_travail")
        
        # Test mapping to JobPosition schema fields
        pos_data = detail_result["job_position_data"]
        self.assertEqual(pos_data["job_title"], "Chef de projet IA")
        self.assertEqual(pos_data["company"], "AI Lab")
        self.assertEqual(pos_data["location"], "Marseille (13)")
        self.assertEqual(pos_data["contract_type"], "CDD")
        self.assertEqual(pos_data["compensation"]["min_salary"], 45000.0)
        self.assertEqual(pos_data["compensation"]["max_salary"], 55000.0)
        self.assertEqual(pos_data["compensation"]["salary_frequency"], "Annuel")
        self.assertIn("Project Management", pos_data["requirements"]["required_skills"])
        self.assertEqual(pos_data["requirements"]["years_of_experience"], 5)
        self.assertEqual(pos_data["company_description"], "We build deep learning models.")

    def test_provider_manager_routing(self):
        manager = JobProviderManager()
        self.assertIn("france_travail", manager.list_providers())
        
        mock_provider = MagicMock()
        mock_provider.get_provider_name.return_value = "custom_platform"
        
        manager.register_provider(mock_provider)
        self.assertIn("custom_platform", manager.list_providers())
        
        # Test routing search
        manager.search_jobs("custom_platform", query="rust")
        mock_provider.search_jobs.assert_called_once_with(
            query="rust",
            department=None,
            contract_type=None,
            page=1,
            limit=25
        )
