"""
Phase 1.5G — Model-neutral knowledge interfaces.

AgentQE code must depend on ``ApplicationKnowledgeBuilder`` and
``ApplicationKnowledgeQuery``, never on a concrete implementation. These
abstractions know nothing about OmniParser, Playwright, Flask, LLM providers,
LlamaIndex, LangGraph, a vector store, or a graph database (§5).

The seam exists so that Phase 2 can add a retrieval-backed query implementation
(or a graph-database-backed one) without touching any caller: the knowledge
model stays the structured source of truth, and retrieval becomes *another*
implementation of the same read-only contract.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agentqe.knowledge.schemas import ApplicationKnowledgeModel


class ApplicationKnowledgeBuilder(ABC):
    """Builds an ``ApplicationKnowledgeModel`` from a ``UnifiedApplicationModel``."""

    @abstractmethod
    def build(self, unified_model: Any) -> ApplicationKnowledgeModel:
        """
        Transform a Phase 1.5F unified model into a semantic knowledge model.

        Args:
            unified_model: An ``agentqe.fusion.schemas.UnifiedApplicationModel``
                or its ``to_dict()`` form. Implementations MUST accept both and
                MUST NOT mutate the input.

        Returns:
            ApplicationKnowledgeModel — references Phase 1.5F entities and raw
            evidence, never replaces them.

        Implementations MUST NOT launch a browser, re-crawl, re-run OmniParser,
        re-extract DOM, or perform any network access (§49). The builder is a
        pure function of its input plus a timestamp.
        """
        raise NotImplementedError

    @abstractmethod
    def get_builder_info(self) -> Dict[str, Any]:
        """
        Builder metadata for ``provenance``.

        Returns:
            Dict with at least: ``builder``, ``knowledge_model_version``,
            ``llm_used``.
        """
        raise NotImplementedError


class ApplicationKnowledgeQuery(ABC):
    """
    Read-only, deterministic query surface over an ``ApplicationKnowledgeModel``.

    Every method must be free of side effects and must return the same result
    for the same model and arguments (§25). Nothing here may fall back to an
    LLM, an embedding model, or a network call.
    """

    # -- entity access ------------------------------------------------------

    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return one entity by its deterministic id, or ``None``."""
        raise NotImplementedError

    @abstractmethod
    def find_entities(
        self,
        entity_type: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return entities matching every supplied filter (AND semantics)."""
        raise NotImplementedError

    # -- relationship access ------------------------------------------------

    @abstractmethod
    def find_relationships(
        self,
        source_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return relationships matching every supplied filter."""
        raise NotImplementedError

    @abstractmethod
    def get_neighbors(self, entity_id: str) -> List[Dict[str, Any]]:
        """
        Return the entities directly connected to ``entity_id`` in either
        direction, each annotated with the connecting relationship.
        """
        raise NotImplementedError

    # -- context access -----------------------------------------------------

    @abstractmethod
    def get_page_context(self, page_id: str) -> Dict[str, Any]:
        """
        Return a compact, self-contained description of one page: its controls,
        forms, APIs, modules, requirements, repository references and
        relationships (§30). Contains no raw DOM, accessibility tree, network
        body, or screenshot content — references only.
        """
        raise NotImplementedError

    @abstractmethod
    def get_context_for_entity(self, entity_id: str) -> Dict[str, Any]:
        """
        Return the generic retrieval context for any entity (§46).

        This is the method Phase 2 will wrap when it builds documents for
        LlamaIndex, so its output must remain JSON-safe and free of raw
        evidence payloads.
        """
        raise NotImplementedError


class KnowledgeModelError(Exception):
    """Raised when a knowledge model cannot be built or loaded."""

    def __init__(self, message: str, error_code: str = "KNOWLEDGE_MODEL_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class KnowledgeBuildError(KnowledgeModelError):
    """Raised by a builder on unrecoverable failure (§39)."""

    def __init__(self, message: str, error_code: str = "KNOWLEDGE_BUILD_ERROR"):
        super().__init__(message, error_code)


__all__ = [
    "ApplicationKnowledgeBuilder",
    "ApplicationKnowledgeQuery",
    "KnowledgeModelError",
    "KnowledgeBuildError",
]
