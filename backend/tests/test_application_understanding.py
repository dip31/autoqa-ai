import pytest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_application_understanding_input_model():
    """Test ApplicationUnderstandingInput model creation and serialization."""
    from agentqe.models.context import ApplicationUnderstandingInput
    
    input_data = ApplicationUnderstandingInput(
        url="https://example.com",
        repo_url="https://github.com/user/repo",
        requirement="Users should be able to login",
        module_name="Authentication",
        metadata={"source": "test"}
    )
    
    assert input_data.url == "https://example.com"
    assert input_data.repo_url == "https://github.com/user/repo"
    assert input_data.requirement == "Users should be able to login"
    assert input_data.module_name == "Authentication"
    
    # Test serialization
    serialized = input_data.to_dict()
    assert serialized["url"] == "https://example.com"
    assert serialized["requirement"] == "Users should be able to login"


def test_application_context_model():
    """Test ApplicationContext model creation and serialization."""
    from agentqe.models.context import ApplicationContext
    
    ctx = ApplicationContext(
        url="https://example.com",
        app_name="Test App",
        app_type="web",
        technology_stack={"frontend": "React", "backend": "Node.js"},
        framework="React",
        modules=["Authentication", "Dashboard"],
        features=[{"name": "Login", "source": "crawl"}],
        requirements=[{"description": "Users can login", "source": "user_input"}],
        user_flows=["Login flow", "Password reset"],
        testable_areas=[{"area": "Login page", "source": "requirement_analysis"}],
        discovered_routes=["/login", "/dashboard", "/api/users"],
        api_endpoints=["/api/login", "/api/logout"],
        forms=[{"action": "/login", "method": "POST", "inputs": [{"type": "email", "name": "email"}]}],
        risk_areas=[{"area": "Authentication", "reason": "Critical flow", "source": "analysis"}],
        evidence={"app_name": ["application_crawl"], "modules": ["application_crawl"]}
    )
    
    assert ctx.url == "https://example.com"
    assert ctx.app_name == "Test App"
    assert ctx.app_type == "web"
    assert "frontend" in ctx.technology_stack
    assert len(ctx.modules) == 2
    
    # Test serialization
    serialized = ctx.to_dict()
    assert serialized["app_name"] == "Test App"
    assert len(serialized["modules"]) == 2
    assert serialized["evidence"]["app_name"] == ["application_crawl"]


def test_application_understanding_interface():
    """Test that IApplicationUnderstanding interface exists and can be implemented."""
    from agentqe.interfaces import IApplicationUnderstanding, ApplicationUnderstandingInput, ApplicationContext
    
    # Verify interface has analyze method
    assert hasattr(IApplicationUnderstanding, 'analyze')
    assert callable(getattr(IApplicationUnderstanding, 'analyze', None))
    
    # Create a minimal implementation for testing
    class TestImpl(IApplicationUnderstanding):
        def analyze(self, input_data: ApplicationUnderstandingInput) -> ApplicationContext:
            return ApplicationContext(
                url=input_data.url or "",
                requirement=input_data.requirement or "",
                app_name="Test App"
            )
    
    impl = TestImpl()
    result = impl.analyze(ApplicationUnderstandingInput(url="https://test.com", requirement="Test requirement"))
    
    assert isinstance(result, ApplicationContext)
    assert result.url == "https://test.com"
    assert result.requirement == "Test requirement"
    assert result.app_name == "Test App"


def test_application_understanding_agent_import():
    """Test that ApplicationUnderstandingAgent can be imported."""
    from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
    
    # Just verify import works and class exists
    assert ApplicationUnderstandingAgent is not None
    assert hasattr(ApplicationUnderstandingAgent, 'analyze')


@patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application')
@patch('agentqe.agents.application_understanding_agent._analyze_requirement')
def test_application_understanding_agent_analyze_with_url(mock_analyze_req, mock_crawl_app):
    """Test ApplicationUnderstandingAgent.analyze with URL input."""
    from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
    from agentqe.models.context import ApplicationUnderstandingInput
    
    # Mock crawl application response (multi-page crawler result)
    mock_crawl_app.return_value = {
        "pages": [{
            "url": "https://example.com",
            "depth": 0,
            "title": "Test Application",
            "page_type": "dashboard",
            "page_type_confidence": "observed",
            "crawl_status": "success",
            "detected_flows": ["Authentication", "Dashboard"],
            "forms": [{"action": "/login", "method": "POST", "inputs": [{"type": "email", "name": "email"}]}],
            "links": [{"target": "https://example.com/api/users", "text": "Users API"}],
            "nav_links": [{"text": "Login", "href": "/login"}, {"text": "Dashboard", "href": "/dashboard"}],
            "buttons": ["Login", "Submit"],
            "inputs": [{"type": "email", "name": "email"}],
            "has_login": True,
            "has_search": False,
            "has_cart": False,
            "has_product": False,
            "main_text": "Welcome to Test Application",
            "dom": {},
            "accessibility_tree": {},
            "ui_insights": {},
        }],
        "navigation_graph": {"nodes": ["https://example.com"], "edges": []},
        "discovered_routes": [
            {"path": "/", "url": "https://example.com", "depth": 0, "page_type": "dashboard", "title": "Test Application", "status": 200, "crawl_status": "success", "evidence_type": "observed", "source": "application_crawl"},
            {"path": "/login", "url": "https://example.com/login", "depth": 1, "page_type": "authentication", "title": "Login", "status": 200, "crawl_status": "not_crawled", "evidence_type": "observed", "source": "application_crawl"},
            {"path": "/dashboard", "url": "https://example.com/dashboard", "depth": 1, "page_type": "dashboard", "title": "Dashboard", "status": 200, "crawl_status": "not_crawled", "evidence_type": "observed", "source": "application_crawl"},
        ],
        "crawl_metadata": {"pages_analyzed": 1, "pages_failed": 0, "pages_discovered": 3, "duration_seconds": 1.0, "max_pages": 10, "max_depth": 2, "same_domain_only": True},
        "warnings": [],
    }
    
    # Mock requirement analysis response
    mock_analyze_req.return_value = {
        "key_user_flows": ["User Login", "Dashboard Navigation"],
        "items": ["Login form validation", "Session management"],
        "risk_areas": ["Authentication bypass", "Session hijacking"],
    }
    
    agent = ApplicationUnderstandingAgent()
    input_data = ApplicationUnderstandingInput(
        url="https://example.com",
        requirement="Users should be able to login securely"
    )
    
    result = agent.analyze(input_data)
    
    # Verify basic structure
    assert result.url == "https://example.com"
    assert result.requirement == "Users should be able to login securely"
    assert result.app_name == "Test Application"
    assert result.app_type == "web"
    assert "Authentication" in result.modules
    assert "Dashboard" in result.modules
    
    # Verify forms were extracted
    assert len(result.forms) > 0
    assert result.forms[0]["action"] == "/login"
    
    # Verify API endpoints extracted
    assert "https://example.com/api/users" in result.api_endpoints
    
    # Verify discovered routes
    assert "/login" in result.discovered_routes
    assert "/dashboard" in result.discovered_routes
    
    # Verify requirements processed
    assert len(result.requirements) > 0
    assert result.requirements[0]["description"] == "Users should be able to login securely"
    
    # Verify user flows
    assert "User Login" in result.user_flows
    assert "Dashboard Navigation" in result.user_flows
    
    # Verify testable areas
    assert len(result.testable_areas) > 0
    
    # Verify risk areas
    assert len(result.risk_areas) > 0
    assert any(r["area"] == "Authentication bypass" for r in result.risk_areas)
    
    # Verify evidence tracking
    assert "title" in result.evidence
    assert "application_crawl" in result.evidence["title"]


def test_application_understanding_agent_with_requirement_only():
    """Test ApplicationUnderstandingAgent with only requirement (no URL, no repo)."""
    from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
    from agentqe.models.context import ApplicationUnderstandingInput
    
    with patch('agentqe.agents.application_understanding_agent._analyze_requirement') as mock_analyze_req:
        mock_analyze_req.return_value = {
            "key_user_flows": ["User Registration"],
            "items": ["Registration form", "Email verification"],
            "risk_areas": ["Weak password policy"],
        }
        
        agent = ApplicationUnderstandingAgent()
        input_data = ApplicationUnderstandingInput(
            requirement="Users should be able to register with email verification"
        )
        
        result = agent.analyze(input_data)
        
        assert result.requirement == "Users should be able to register with email verification"
        assert result.app_type == "unknown"  # No URL, no repo
        assert len(result.requirements) > 0
        assert "User Registration" in result.user_flows


def test_serialization_roundtrip():
    """Test that models can be serialized and deserialized."""
    from agentqe.models.context import ApplicationContext, ApplicationUnderstandingInput
    
    original_input = ApplicationUnderstandingInput(
        url="https://example.com",
        requirement="Test requirement",
        repo_url="https://github.com/test/repo",
        module_name="TestModule"
    )
    
    # Serialize and deserialize input
    input_dict = original_input.to_dict()
    restored_input = ApplicationUnderstandingInput(**input_dict)
    
    assert restored_input.url == original_input.url
    assert restored_input.requirement == original_input.requirement
    assert restored_input.repo_url == original_input.repo_url
    
    # Test ApplicationContext serialization
    original_ctx = ApplicationContext(
        url="https://example.com",
        app_name="Test",
        modules=["Auth", "Dashboard"],
        evidence={"app_name": ["crawl"]}
    )
    
    ctx_dict = original_ctx.to_dict()
    # Note: ApplicationContext has many optional fields with defaults, 
    # so we only test the fields we set
    assert ctx_dict["url"] == "https://example.com"
    assert ctx_dict["app_name"] == "Test"
    assert ctx_dict["modules"] == ["Auth", "Dashboard"]
    assert ctx_dict["evidence"] == {"app_name": ["crawl"]}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])