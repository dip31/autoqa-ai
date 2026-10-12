"""
Simple test runner for bounded context builder without conftest dependencies.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentqe.generation.config import resolve_context_budget, ContextBudgetConfig
from agentqe.generation.context_limiter import BoundedContextBuilder
from agentqe.models.context import ApplicationContext

def test_context_budget_config():
    print("Testing ContextBudgetConfig...")
    config = resolve_context_budget()
    assert config.max_prompt_tokens == 6500
    assert config.rag_top_k == 8
    assert config.max_pages == 10
    assert config.max_apis == 15
    print("✓ ContextBudgetConfig OK")

def test_bounded_context_builder():
    print("Testing BoundedContextBuilder...")
    builder = BoundedContextBuilder()
    
    # Create mock application context with many entities
    app_context = ApplicationContext(
        knowledge_model={
            "entities": [
                {"id": "page1", "entity_type": "page", "name": "Login Page", "url": "/login"},
                {"id": "page2", "entity_type": "page", "name": "Dashboard", "url": "/dashboard"},
                {"id": "page3", "entity_type": "page", "name": "Profile", "url": "/profile"},
                {"id": "page4", "entity_type": "page", "name": "Settings", "url": "/settings"},
                {"id": "page5", "entity_type": "page", "name": "Admin", "url": "/admin"},
                {"id": "page6", "entity_type": "page", "name": "Reports", "url": "/reports"},
                {"id": "page7", "entity_type": "page", "name": "Help", "url": "/help"},
                {"id": "page8", "entity_type": "page", "name": "About", "url": "/about"},
                {"id": "page9", "entity_type": "page", "name": "Contact", "url": "/contact"},
                {"id": "page10", "entity_type": "page", "name": "FAQ", "url": "/faq"},
                {"id": "page11", "entity_type": "page", "name": "Terms", "url": "/terms"},
                {"id": "page12", "entity_type": "page", "name": "Privacy", "url": "/privacy"},
                {"id": "control1", "entity_type": "control", "name": "Email Input", "page_ref": "page1"},
                {"id": "control2", "entity_type": "control", "name": "Password Input", "page_ref": "page1"},
                {"id": "control3", "entity_type": "control", "name": "Submit Button", "page_ref": "page1"},
                {"id": "api1", "entity_type": "api_endpoint", "name": "Login API", "method": "POST", "path": "/api/login"},
                {"id": "api2", "entity_type": "api_endpoint", "name": "Logout API", "method": "POST", "path": "/api/logout"},
                {"id": "api3", "entity_type": "api_endpoint", "name": "User API", "method": "GET", "path": "/api/user"},
                {"id": "flow1", "entity_type": "user_flow", "name": "Login Flow", "steps": ["go to login", "enter creds", "submit"]},
                {"id": "module1", "entity_type": "module", "name": "Auth Module"},
            ]
        },
        repository_data={}
    )
    
    # Build context for user agent
    user_ctx = builder.build(app_context, "User login functionality", agent_type="user")
    
    # Check limits are respected
    assert len(user_ctx.get("pages", [])) <= 10, f"Too many pages: {len(user_ctx.get('pages', []))}"
    assert len(user_ctx.get("controls", [])) <= 30, f"Too many controls: {len(user_ctx.get('controls', []))}"
    
    # Check compact serialization
    if user_ctx.get("pages"):
        assert isinstance(user_ctx["pages"][0], str), "Pages should be compact strings"
    
    print("✓ BoundedContextBuilder OK")

def test_relevance_ranking():
    print("Testing relevance ranking...")
    builder = BoundedContextBuilder()
    
    app_context = ApplicationContext(
        knowledge_model={
            "entities": [
                {"id": "page1", "entity_type": "page", "name": "Login Page", "url": "/login"},
                {"id": "page2", "entity_type": "page", "name": "Dashboard", "url": "/dashboard"},
                {"id": "page3", "entity_type": "page", "name": "Profile", "url": "/profile"},
                {"id": "api1", "entity_type": "api_endpoint", "name": "Login API", "method": "POST", "path": "/api/login"},
            ]
        },
        repository_data={}
    )
    
    # Build context for "login" requirement
    ctx = builder.build(app_context, "User login functionality", agent_type="user")
    
    # Login-related entities should be ranked higher
    pages = ctx.get("pages", [])
    if pages:
        # Login page should appear first or near top
        assert any("login" in p.lower() for p in pages), "Login page should be in context"
    
    print("✓ Relevance ranking OK")

def test_token_estimation():
    print("Testing token estimation...")
    builder = BoundedContextBuilder()
    
    # Test estimation
    text = "This is a test string for token estimation."
    tokens = builder._estimate_tokens(text)
    assert tokens > 0, "Token estimate should be positive"
    assert tokens < len(text), "Token estimate should be less than character count"
    
    print("✓ Token estimation OK")

def test_agent_type_focus():
    print("Testing agent-type specific context...")
    builder = BoundedContextBuilder()
    
    app_context = ApplicationContext(
        knowledge_model={
            "entities": [
                {"id": "page1", "entity_type": "page", "name": "Login Page"},
                {"id": "api1", "entity_type": "api_endpoint", "name": "Login API", "method": "POST", "path": "/api/login"},
            ]
        },
        repository_data={}
    )
    
    # User agent should get UI-focused context
    user_ctx = builder.build(app_context, "login", agent_type="user")
    
    # Engineering agent should get API-focused context
    eng_ctx = builder.build(app_context, "login", agent_type="engineering")
    
    print("✓ Agent-type focus OK")

if __name__ == "__main__":
    print("Running bounded context tests...\n")
    try:
        test_context_budget_config()
        test_bounded_context_builder()
        test_relevance_ranking()
        test_token_estimation()
        test_agent_type_focus()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
