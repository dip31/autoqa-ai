"""
Simple test runner for generation service with bounded context without conftest dependencies.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentqe.generation.config import resolve_context_budget
from agentqe.generation.context_limiter import BoundedContextBuilder
from agentqe.generation.models import GroqTestGenerationModel, GenerationError
from agentqe.models.context import ApplicationContext

def test_generation_config():
    print("Testing generation config...")
    config = resolve_context_budget()
    assert config.max_prompt_tokens == 6500
    assert config.rag_top_k == 8
    print("✓ Generation config OK")

def test_bounded_context_with_large_app():
    print("Testing bounded context with large application...")
    builder = BoundedContextBuilder()
    
    # Create a large application context (simulating the problem case)
    entities = []
    for i in range(100):
        entities.append({"id": f"page{i}", "entity_type": "page", "name": f"Page {i}", "url": f"/page{i}"})
    for i in range(200):
        entities.append({"id": f"control{i}", "entity_type": "control", "name": f"Control {i}", "page_ref": f"page{i//2}"})
    for i in range(50):
        entities.append({"id": f"api{i}", "entity_type": "api_endpoint", "name": f"API {i}", "method": "GET", "path": f"/api{i}"})
    for i in range(30):
        entities.append({"id": f"flow{i}", "entity_type": "user_flow", "name": f"Flow {i}", "steps": []})
    for i in range(20):
        entities.append({"id": f"module{i}", "entity_type": "module", "name": f"Module {i}"})
    
    app_context = ApplicationContext(
        knowledge_model={"entities": entities},
        repository_data={"files": [{"path": f"file{i}.py"} for i in range(50)]}
    )
    
    # Build context for user agent
    user_ctx = builder.build(app_context, "User login functionality", agent_type="user")
    
    # Verify limits are respected
    assert len(user_ctx.get("pages", [])) <= 10, f"Too many pages: {len(user_ctx.get('pages', []))}"
    assert len(user_ctx.get("controls", [])) <= 30, f"Too many controls: {len(user_ctx.get('controls', []))}"
    assert len(user_ctx.get("apis", [])) <= 15, f"Too many APIs: {len(user_ctx.get('apis', []))}"
    assert len(user_ctx.get("flows", [])) <= 8, f"Too many flows: {len(user_ctx.get('flows', []))}"
    
    # Verify compact serialization
    if user_ctx.get("pages"):
        assert isinstance(user_ctx["pages"][0], str), "Pages should be compact strings"
    
    print("✓ Bounded context with large app OK")

def test_token_budget_enforcement():
    print("Testing token budget enforcement...")
    builder = BoundedContextBuilder()
    
    # Create context that would exceed budget
    entities = []
    for i in range(100):
        entities.append({"id": f"page{i}", "entity_type": "page", "name": f"Very long page name with lots of details {i}", "url": f"/page{i}"})
    
    app_context = ApplicationContext(
        knowledge_model={"entities": entities},
        repository_data={"files": [{"path": f"file{i}.py" * 10} for i in range(100)]}
    )
    
    ctx = builder.build(app_context, "test requirement", agent_type="user")
    
    # Estimate tokens
    estimated = builder._estimate_tokens(ctx)
    
    # Should be within budget
    assert estimated <= builder.budget_config.max_prompt_tokens, f"Context exceeds budget: {estimated} > {builder.budget_config.max_prompt_tokens}"
    
    print(f"  Estimated tokens: {estimated} (budget: {builder.budget_config.max_prompt_tokens})")
    print("✓ Token budget enforcement OK")

def test_generation_error_handling():
    print("Testing generation error handling...")
    
    # Test GenerationError creation
    error = GenerationError("PROMPT_TOO_LARGE", "Test message")
    assert error.error_code == "PROMPT_TOO_LARGE"
    assert error.message == "Test message"
    
    print("✓ Generation error handling OK")

def test_model_token_estimation():
    print("Testing model token estimation...")
    
    # This will fail if GROQ_API_KEY is not set, but we can test the estimation logic
    try:
        model = GroqTestGenerationModel()
        
        # Test estimation
        prompt = "This is a test prompt for token estimation."
        tokens = model._estimate_tokens(prompt, "System prompt")
        assert tokens > 0, "Token estimate should be positive"
        
        print(f"  Estimated tokens for test prompt: {tokens}")
        print("✓ Model token estimation OK")
    except ValueError as e:
        if "GROQ_API_KEY" in str(e):
            print("  Skipping (GROQ_API_KEY not set)")
            print("✓ Model token estimation skipped (OK)")
        else:
            raise

if __name__ == "__main__":
    print("Running generation service tests...\n")
    try:
        test_generation_config()
        test_bounded_context_with_large_app()
        test_token_budget_enforcement()
        test_generation_error_handling()
        test_model_token_estimation()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
