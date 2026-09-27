"""
Phase 1.5F — Model-neutral evidence fusion interface.

AgentQE code must depend on ``EvidenceFusionEngine``, never on a concrete
fusion implementation. The interface deliberately knows nothing about
OmniParser, Playwright, OpenAI, Gemini, Groq, LangChain or LlamaIndex: it
consumes *structured evidence* (an ``ApplicationContext``) and returns a
``UnifiedApplicationModel``.

A future LLM/VLM-backed engine can implement the same interface and operate on
top of the structured evidence layer produced here.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from agentqe.fusion.schemas import UnifiedApplicationModel


class EvidenceFusionEngine(ABC):
    """Abstract base class for cross-modal evidence fusion engines."""

    @abstractmethod
    def fuse(self, application_context: Any) -> UnifiedApplicationModel:
        """
        Correlate the evidence in ``application_context`` into a unified model.

        Args:
            application_context: An ``agentqe.models.context.ApplicationContext``
                (or any object/dict exposing the same fields: ``pages``,
                ``navigation_graph``, ``requirements``, ``repository_data``,
                ``modules``, ``features``, ``user_flows`` ...).

        Returns:
            UnifiedApplicationModel — references raw evidence, never replaces it.

        Implementations MUST NOT mutate ``application_context`` evidence.
        """
        raise NotImplementedError

    @abstractmethod
    def get_engine_info(self) -> Dict[str, Any]:
        """
        Engine metadata for ``fusion_metadata``.

        Returns:
            Dict with at least: ``engine``, ``fusion_version``, ``llm_used``.
        """
        raise NotImplementedError


class EvidenceFusionError(Exception):
    """Raised by fusion engines on unrecoverable failure."""

    def __init__(self, message: str, error_code: str = "FUSION_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
