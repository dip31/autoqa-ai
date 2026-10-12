"""
Phase 3/4 — AgentQE LLM Generation Configuration.

Single source of truth for which Groq model the generation agents use
and context budget limits.
"""

import os
from dataclasses import dataclass


DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

# Context budget configuration
DEFAULT_MAX_PROMPT_TOKENS = 6500  # Safe headroom below 8000 limit
DEFAULT_RAG_TOP_K = 8


@dataclass(frozen=True)
class LLMConfig:
    """Resolved LLM configuration."""
    model_name: str
    temperature: float = 0.2
    response_format: str = "json_object"

    @property
    def is_valid(self) -> bool:
        return bool(self.model_name)


@dataclass(frozen=True)
class ContextBudgetConfig:
    """Context budget configuration for generation."""
    max_prompt_tokens: int
    rag_top_k: int
    
    # Per-entity type limits
    max_pages: int = 10
    max_flows: int = 8
    max_controls: int = 30
    max_forms: int = 10
    max_apis: int = 15
    max_modules: int = 10
    max_risks: int = 10
    max_repo_files: int = 10
    max_repo_symbols: int = 20
    max_evidence_items: int = 20


def resolve_llm_config() -> LLMConfig:
    """
    Build the effective LLM configuration from defaults + environment.
    
    The default is a currently supported Groq model.
    """
    model_name = (os.environ.get("AGENTQE_GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
    if not model_name:
        model_name = DEFAULT_GROQ_MODEL
    
    temperature = float(os.environ.get("AGENTQE_GROQ_TEMPERATURE", "0.2"))
    
    return LLMConfig(
        model_name=model_name,
        temperature=temperature,
    )


def resolve_context_budget() -> ContextBudgetConfig:
    """
    Build the effective context budget configuration from defaults + environment.
    
    The max_prompt_tokens should be safely below the provider's limit
    to leave room for system instructions, user prompt, and response.
    """
    max_prompt_tokens = int(os.environ.get(
        "AGENTQE_GENERATION_MAX_PROMPT_TOKENS",
        str(DEFAULT_MAX_PROMPT_TOKENS)
    ))
    
    rag_top_k = int(os.environ.get(
        "AGENTQE_GENERATION_RAG_TOP_K",
        str(DEFAULT_RAG_TOP_K)
    ))
    
    # Optional per-entity limits
    max_pages = int(os.environ.get("AGENTQE_GENERATION_MAX_PAGES", str(10)))
    max_flows = int(os.environ.get("AGENTQE_GENERATION_MAX_FLOWS", str(8)))
    max_controls = int(os.environ.get("AGENTQE_GENERATION_MAX_CONTROLS", str(30)))
    max_forms = int(os.environ.get("AGENTQE_GENERATION_MAX_FORMS", str(10)))
    max_apis = int(os.environ.get("AGENTQE_GENERATION_MAX_APIS", str(15)))
    max_modules = int(os.environ.get("AGENTQE_GENERATION_MAX_MODULES", str(10)))
    
    return ContextBudgetConfig(
        max_prompt_tokens=max_prompt_tokens,
        rag_top_k=rag_top_k,
        max_pages=max_pages,
        max_flows=max_flows,
        max_controls=max_controls,
        max_forms=max_forms,
        max_apis=max_apis,
        max_modules=max_modules,
    )


__all__ = [
    "DEFAULT_GROQ_MODEL",
    "DEFAULT_MAX_PROMPT_TOKENS",
    "DEFAULT_RAG_TOP_K",
    "LLMConfig",
    "ContextBudgetConfig",
    "resolve_llm_config",
    "resolve_context_budget",
]