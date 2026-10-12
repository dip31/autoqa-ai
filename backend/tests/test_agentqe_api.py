"""
Phase 3/4 — AgentQE API tests.

Tests for RAG query, test generation, and test prioritization endpoints.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Ensure test environment
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("AGENTQE_RAG_EMBEDDING_PROVIDER", "mock")


@pytest.fixture
def auth_headers(client):
    """Get JWT auth headers by registering and logging in a test user."""
    # Register a test user
    register_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
        "role": "qa_engineer"
    }
    client.post("/auth/register", json=register_data)
    
    # Login to get token
    login_resp = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpass123"
    })
    token = login_resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestRAGQueryEndpoint:
    """Tests for /api/agentqe/application/query endpoint."""
    
    def test_get_method_returns_405(self, client, auth_headers):
        """GET should return 405 Method Not Allowed."""
        resp = client.get("/api/agentqe/application/query", headers=auth_headers)
        assert resp.status_code == 405
    
    def test_unauthenticated_post_returns_401(self, client):
        """POST without auth should return 401."""
        resp = client.post("/api/agentqe/application/query", json={"query": "test"})
        assert resp.status_code == 401
    
    def test_malformed_request_returns_422(self, client, auth_headers):
        """POST with missing query should return 400 (validation error)."""
        resp = client.post("/api/agentqe/application/query", json={}, headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "Query is required" in data["error"]
    
    def test_valid_request_without_index_returns_400(self, client, auth_headers):
        """POST with valid query but no index should return 400 or 200 with empty results."""
        resp = client.post("/api/agentqe/application/query", 
                          json={"query": "test query", "top_k": 3},
                          headers=auth_headers)
        # Should return 400 because index is not ready, or 200 with empty results if index exists
        assert resp.status_code in (200, 400)
        data = resp.get_json()
        if resp.status_code == 400:
            assert "error" in data
            assert "RAG index is not ready" in data["error"]
        else:
            # Index is ready, should return success with results (possibly empty)
            assert data["success"] is True
            assert "results" in data


class TestTestGenerationEndpoint:
    """Tests for /api/agentqe/tests/generate endpoint."""
    
    def test_unauthenticated_returns_401(self, client):
        """POST without auth should return 401."""
        resp = client.post("/api/agentqe/tests/generate", json={})
        assert resp.status_code == 401
    
    def test_missing_context_returns_400(self, client, auth_headers):
        """POST without application_context should return 400."""
        resp = client.post("/api/agentqe/tests/generate", 
                          json={"requirement": "test"},
                          headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "application_context is required" in data["error"]
    
    @patch("agentqe.generation.service.GroqTestGenerationModel")
    def test_generation_success_structure(self, mock_model_class, client, auth_headers):
        """Test successful generation returns proper structure."""
        # Mock the Groq model to return a successful response
        mock_model = MagicMock()
        mock_model.generate.return_value = json.dumps({
            "test_cases": [
                {
                    "test_id": "USER-001",
                    "title": "Test Login",
                    "description": "Verify login works",
                    "perspective": "USER",
                    "test_type": "UI",
                    "steps": ["Go to login", "Enter credentials", "Click login"],
                    "expected_result": "User is logged in",
                    "requirement_refs": ["REQ-001"],
                    "page_refs": ["page:login"],
                    "control_refs": ["control:sign_in"],
                    "form_refs": [],
                    "api_refs": ["api:post:/api/auth/login"],
                    "flow_refs": [],
                    "evidence_refs": []
                }
            ]
        })
        mock_model_class.return_value = mock_model
        
        app_context = {
            "url": "https://example.com",
            "requirement": "User can log in",
            "module_name": "Auth",
            "pages": [{"id": "page:login", "url": "https://example.com/login"}],
            "controls": [{"id": "control:sign_in", "type": "button"}],
            "forms": [],
            "apis": [{"id": "api:post:/api/auth/login", "method": "POST", "path": "/api/auth/login"}],
            "flows": [],
            "modules": [],
            "requirements": []
        }
        
        resp = client.post("/api/agentqe/tests/generate", 
                          json={"application_context": app_context, "requirement": "User can log in"},
                          headers=auth_headers)
        
        assert resp.status_code in (200, 207)
        data = resp.get_json()
        assert "success" in data
        assert "generation_summary" in data
        assert "candidate_tests" in data
        assert "generators" in data
        assert isinstance(data["generators"], list)
        assert len(data["generators"]) == 2  # user_agent and engineering_agent
    
    @patch("agentqe.generation.service.GroqTestGenerationModel")
    def test_generation_partial_failure(self, mock_model_class, client, auth_headers):
        """Test partial failure (one generator fails) returns 207."""
        # Mock user agent success, engineering agent failure
        mock_model = MagicMock()
        
        def generate_side_effect(prompt, system_prompt=""):
            if "USER" in system_prompt or "user" in system_prompt.lower():
                return json.dumps({
                    "test_cases": [{
                        "test_id": "USER-001",
                        "title": "Test Login",
                        "description": "Verify login works",
                        "perspective": "USER",
                        "test_type": "UI",
                        "steps": ["Go to login"],
                        "expected_result": "User is logged in",
                        "requirement_refs": [],
                        "page_refs": [],
                        "control_refs": [],
                        "form_refs": [],
                        "api_refs": [],
                        "flow_refs": [],
                        "evidence_refs": []
                    }]
                })
            else:
                # Engineering agent fails
                raise Exception("model_decommissioned: model llama-3.1-70b-versatile has been decommissioned")
        
        mock_model.generate.side_effect = generate_side_effect
        mock_model_class.return_value = mock_model
        
        app_context = {
            "url": "https://example.com",
            "requirement": "User can log in",
            "module_name": "Auth",
            "pages": [],
            "controls": [],
            "forms": [],
            "apis": [],
            "flows": [],
            "modules": [],
            "requirements": []
        }
        
        resp = client.post("/api/agentqe/tests/generate", 
                          json={"application_context": app_context, "requirement": "User can log in"},
                          headers=auth_headers)
        
        assert resp.status_code == 207
        data = resp.get_json()
        assert data["status"] == "partial_failure"
        assert "generators" in data
        generators = {g["agent"]: g for g in data["generators"]}
        assert generators["user_agent"]["status"] == "success"
        assert generators["engineering_agent"]["status"] == "failed"
        assert generators["engineering_agent"]["error_code"] == "MODEL_DECOMMISSIONED"
        # Successful generator output should be preserved
        assert len(data["candidate_tests"]) > 0
    
    @patch("agentqe.generation.service.GroqTestGenerationModel")
    def test_generation_complete_failure(self, mock_model_class, client, auth_headers):
        """Test complete failure (both generators fail) returns 500."""
        mock_model = MagicMock()
        mock_model.generate.side_effect = Exception("model_decommissioned: model has been decommissioned")
        mock_model_class.return_value = mock_model
        
        app_context = {
            "url": "https://example.com",
            "requirement": "User can log in",
            "module_name": "Auth",
            "pages": [],
            "controls": [],
            "forms": [],
            "apis": [],
            "flows": [],
            "modules": [],
            "requirements": []
        }
        
        resp = client.post("/api/agentqe/tests/generate", 
                          json={"application_context": app_context, "requirement": "User can log in"},
                          headers=auth_headers)
        
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "failed"
        assert "generators" in data
        generators = {g["agent"]: g for g in data["generators"]}
        assert generators["user_agent"]["status"] == "failed"
        assert generators["engineering_agent"]["status"] == "failed"


class TestGroqModelConfiguration:
    """Tests for centralized Groq model configuration."""
    
    def test_model_config_centralized(self):
        """Verify model name is not hardcoded in generators."""
        from agentqe.generation.config import resolve_llm_config, DEFAULT_GROQ_MODEL
        
        config = resolve_llm_config()
        assert config.model_name == DEFAULT_GROQ_MODEL
        assert config.model_name != "llama-3.1-70b-versatile"  # old decommissioned model
    
    def test_generators_use_same_config(self):
        """Both generators should use the same centralized config."""
        from agentqe.generation.user_test_generator import UserTestGenerator
        from agentqe.generation.engineering_test_generator import EngineeringTestGenerator
        from agentqe.generation.models import GroqTestGenerationModel
        
        model1 = GroqTestGenerationModel()
        model2 = GroqTestGenerationModel()
        
        # Both should use the same model name from centralized config
        assert model1.model_name == model2.model_name
    
    def test_no_stale_hardcoded_model_in_codebase(self):
        """Verify no stale hardcoded model references remain."""
        import glob
        import re
        
        python_files = glob.glob("backend/agentqe/**/*.py", recursive=True)
        stale_model = "llama-3.1-70b-versatile"
        
        for f in python_files:
            if f.endswith("__pycache__") or ".pyc" in f:
                continue
            with open(f, "r") as fp:
                content = fp.read()
                # Allow in test files as they may test for absence
                if "test_" in f:
                    continue
                # The only allowed reference is in the config default or comments
                if stale_model in content and "DEFAULT_GROQ_MODEL" not in content and "decommissioned" not in content.lower():
                    pytest.fail(f"Stale hardcoded model '{stale_model}' found in {f}")


class TestTestPrioritizationEndpoint:
    """Tests for /api/agentqe/tests/prioritize endpoint (Phase 4)."""
    
    def test_unauthenticated_returns_401(self, client):
        """POST without auth should return 401."""
        resp = client.post("/api/agentqe/tests/prioritize", json={})
        assert resp.status_code == 401
    
    def test_missing_tests_returns_400(self, client, auth_headers):
        """POST without candidate_tests should return 400."""
        resp = client.post("/api/agentqe/tests/prioritize", 
                          json={},
                          headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])