import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_list_providers_endpoint(client):
    response = client.get(
        "/api/jobs/providers",
        headers={"X-Tenant-ID": "test-tenant-123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "france_travail" in data["providers"]


@patch("infrastructure.jobs.search.providers.manager.JobProviderManager.search_jobs")
def test_search_jobs_endpoint(mock_search, client):
    mock_search.return_value = {
        "meta": {"count": 1, "page": 1, "total": 1},
        "results": [
            {
                "id": "123",
                "title": "Backend Dev",
                "company": "FastAPI Inc.",
                "location": "Paris",
                "contract_type": "CDI",
                "url": "https://example.com/job/123"
            }
        ]
    }

    payload = {
        "provider": "france_travail",
        "query": "backend",
        "department": "75",
        "contract_type": "CDI",
        "page": 1,
        "limit": 10
    }
    
    response = client.post(
        "/api/jobs/search",
        json=payload,
        headers={"X-Tenant-ID": "test-tenant-123"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 1
    assert data["results"][0]["title"] == "Backend Dev"
    mock_search.assert_called_once_with(
        provider_name="france_travail",
        query="backend",
        department="75",
        contract_type="CDI",
        page=1,
        limit=10
    )


@patch("infrastructure.jobs.search.providers.manager.JobProviderManager.get_job_detail")
def test_get_job_detail_endpoint(mock_get_detail, client):
    mock_get_detail.return_value = {
        "provider": "france_travail",
        "raw_data": {},
        "standard_info": {
            "id": "456",
            "title": "ML Engineer"
        },
        "job_position_data": {
            "job_title": "ML Engineer",
            "company": "DeepTech",
            "location": "Paris",
            "contract_type": "CDI",
            "requirements": {
                "required_skills": ["Python"]
            }
        }
    }

    response = client.get(
        "/api/jobs/search/france_travail/456",
        headers={"X-Tenant-ID": "test-tenant-123"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["standard_info"]["title"] == "ML Engineer"
    assert data["job_position_data"]["company"] == "DeepTech"
    mock_get_detail.assert_called_once_with(provider_name="france_travail", job_id="456")


@patch("infrastructure.jobs.search.agent.JobSearchAgent.run_chat_loop")
def test_search_chat_endpoint(mock_chat, client):
    mock_chat.return_value = "Here are some nice Python jobs in Paris:\n- Job 1\n- Job 2"

    payload = {
        "message": "Find python developer jobs in Paris"
    }

    # Patch ChatGoogleGenerativeAI to avoid network call during initialization
    with patch("infrastructure.agents.base_agents.ChatGoogleGenerativeAI"):
        response = client.post(
            "/api/jobs/search/chat",
            json=payload,
            headers={"X-Tenant-ID": "test-tenant-123"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "history" in data
    assert "nice Python jobs" in data["response"]
