import pytest
import json
from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest
from agentqe.agents.test_planning_agent import TestPlanningAgent
from agentqe.agents.user_agents import UserAgent
from agentqe.agents.engineering_agent import EngineeringQAAgent
from agentqe.pool.candidate_pool import CandidateTestPool
from agentqe.enrichment.enricher import TestEnricher
from app import app


@pytest.fixture
def mock_context():
    return ApplicationContext(
        url="http://example.com",
        module_name="Auth",
        requirement="Login with valid credentials",
        features=[{"name": "Login", "source": "inferred"}],
        user_flows=["Login -> Dashboard"],
        api_endpoints=["/api/login"],
        forms=[{"name": "LoginForm", "inputs": [{"name": "username"}, {"name": "password"}]}],
        risk_areas=["Authentication Bypass"]
    )

def test_test_plan_generation(mock_context):
    planner = TestPlanningAgent()
    plan = planner.plan(mock_context)
    
    assert plan["module"] == "Auth"
    assert len(plan["objectives"]) > 0
    assert any(obj.get("feature") == "Login" for obj in plan["objectives"])
    assert any(obj.get("api_endpoint") == "/api/login" for obj in plan["objectives"])
    assert any(obj.get("form") == "LoginForm" for obj in plan["objectives"])

def test_candidate_test_serialization():
    tc = CandidateTest(
        test_id="TC-001",
        title="Test Login",
        perspective="USER",
        test_type="UI",
        target="Auth",
        source_agent="UserAgent",
        evidence={"source": "requirement"}
    )
    
    serialized = tc.to_dict()
    assert serialized["test_id"] == "TC-001"
    assert serialized["perspective"] == "USER"
    assert serialized["test_type"] == "UI"

def test_user_perspective_agent(mock_context, monkeypatch):
    agent = UserAgent()
    
    def mock_generate_testcases(req):
        return {
            "testcases": [
                {
                    "title": "Valid Login",
                    "objective": "Verify user can login",
                    "category": "UI",
                    "steps": ["Enter username", "Enter password", "Click Login"],
                    "expected_result": "Dashboard is displayed"
                }
            ]
        }
        
    monkeypatch.setattr("agentqe.agents.user_agents.generate_testcases", mock_generate_testcases)
    
    tests = agent.generate(mock_context, {})
    assert len(tests) == 1
    assert tests[0].perspective == "USER"
    assert tests[0].title == "Valid Login"

def test_user_perspective_agent_fallback(mock_context, monkeypatch):
    agent = UserAgent()
    
    def mock_generate_testcases(req):
        raise Exception("LLM Error")
        
    monkeypatch.setattr("agentqe.agents.user_agents.generate_testcases", mock_generate_testcases)
    
    tests = agent.generate(mock_context, {})
    assert len(tests) == 1
    assert tests[0].perspective == "USER"
    assert tests[0].evidence["fallback"] == "generator_failed"

def test_engineering_qa_agent(mock_context):
    agent = EngineeringQAAgent()
    tests = agent.generate(mock_context, {})
    
    # Should generate API tests and Form validation tests based on mock_context
    assert len(tests) >= 2
    assert any(tc.test_type == "API" for tc in tests)
    assert any(tc.test_type == "INTEGRATION" for tc in tests)
    assert all(tc.perspective == "ENGINEERING" for tc in tests)

def test_candidate_pool_merging_and_deduplication():
    pool = CandidateTestPool()
    
    user_tests = [
        CandidateTest(test_id="U1", title="Same Test", test_type="UI", target="Auth", perspective="USER"),
        CandidateTest(test_id="U2", title="Unique User Test", test_type="UI", target="Auth", perspective="USER")
    ]
    
    eng_tests = [
        CandidateTest(test_id="E1", title="Same Test", test_type="UI", target="Auth", perspective="ENGINEERING"),
        CandidateTest(test_id="E2", title="Unique Eng Test", test_type="API", target="Auth", perspective="ENGINEERING")
    ]
    
    merged = pool.merge(user_tests, eng_tests)
    
    # "Same Test" should be deduplicated based on title, type, target
    assert len(merged) == 3
    titles = [t.title for t in merged]
    assert "Same Test" in titles
    assert "Unique User Test" in titles
    assert "Unique Eng Test" in titles

def test_test_enricher():
    enricher = TestEnricher()
    tests = [
        CandidateTest(test_id="1", title="API Test", test_type="API"),
        CandidateTest(test_id="2", title="UI Test", test_type="UI", priority="High")
    ]
    
    enriched = enricher.enrich(tests)
    assert enriched[0].execution_cost == 2.0
    assert enriched[1].execution_cost == 4.0
    assert enriched[1].risk_score == 0.9

def test_api_endpoint_missing_context():
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "test-secret"
    
    with app.test_client() as client:
        # Mock auth
        from flask_jwt_extended import create_access_token
        with app.app_context():
            token = create_access_token(identity="1")
            
        res = client.post("/api/agentqe/tests/generate", json={}, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 400
        assert "application_context is required" in res.get_json()["error"]

def test_api_endpoint_success(mock_context, monkeypatch):
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "test-secret"
    
    def mock_generate_testcases(req):
        return {"testcases": [{"title": "Mocked test"}]}
        
    monkeypatch.setattr("agentqe.agents.user_agents.generate_testcases", mock_generate_testcases)
    
    with app.test_client() as client:
        # Mock auth
        from flask_jwt_extended import create_access_token
        with app.app_context():
            token = create_access_token(identity="1")
            
        payload = {"application_context": mock_context.to_dict()}
        res = client.post("/api/agentqe/tests/generate", json=payload, headers={"Authorization": f"Bearer {token}"})
        
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "test_plan" in data
        assert "user_tests" in data
        assert "engineering_tests" in data
        assert "candidate_tests" in data
        assert len(data["candidate_tests"]) > 0
