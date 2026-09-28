"""
Phase 1.5G — Application Knowledge Model / semantic application graph.

Phase 1.5F (``agentqe.fusion``) answers *"what evidence did we collect, and how
do the evidence sources correlate?"*. Phase 1.5G answers a different question:
*"what does this application contain, and how are its concepts related?"*

The knowledge model is therefore a **second layer**, not a rename. It sits on
top of the ``UnifiedApplicationModel`` and never replaces it — both are attached
to ``ApplicationContext`` and both are returned by the API.

Typical use::

    from agentqe.fusion import DeterministicEvidenceFusionEngine
    from agentqe.knowledge import (
        DeterministicApplicationKnowledgeBuilder,
        DeterministicKnowledgeQuery,
        validate_knowledge_model,
    )

    unified = DeterministicEvidenceFusionEngine().fuse(application_context)

    knowledge = DeterministicApplicationKnowledgeBuilder().build(unified)
    report = validate_knowledge_model(knowledge)

    query = DeterministicKnowledgeQuery(knowledge)
    context = query.get_page_context("page:login")

Guarantees
----------
* **Deterministic** — same unified model in, same ids, counts, indexes and
  serialized bytes out (see ``deterministic_fingerprint``).
* **Traceable** — every entity records ``source_entity_id`` and
  ``evidence_refs``; every relationship records either a
  ``source_relationship_id`` or a ``derivation``.
* **Honest** — ``observed`` / ``inferred`` / ``unknown`` is copied, never
  upgraded; ``confidence`` stays ``None`` when it was ``None``.
* **Offline** — no LLM, no embeddings, no vector store, no graph database, no
  browser, no network, no OmniParser. Building the knowledge model re-reads
  nothing; it only restructures what fusion already produced.
"""

from agentqe.knowledge.builder import (
    DeterministicApplicationKnowledgeBuilder,
    KnowledgeLimits,
)
from agentqe.knowledge.index import KnowledgeIndex
from agentqe.knowledge.interfaces import (
    ApplicationKnowledgeBuilder,
    ApplicationKnowledgeQuery,
    KnowledgeBuildError,
    KnowledgeModelError,
)
from agentqe.knowledge.knowledge_model import GraphEdge, KnowledgeGraph, build_summaries
from agentqe.knowledge.query import DEFAULT_RESULT_LIMIT, DeterministicKnowledgeQuery
from agentqe.knowledge.schemas import (
    ASSOCIATED_WITH,
    BELONGS_TO,
    CALLS,
    CONTAINS,
    DEPENDS_ON,
    DERIVATION_KINDS,
    DERIVATION_STRUCTURAL,
    DERIVATION_TRANSLATED,
    ENTITY_API_ENDPOINT,
    ENTITY_APPLICATION,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_ID_PREFIXES,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REPOSITORY_SYMBOL,
    ENTITY_REQUIREMENT,
    ENTITY_TECHNOLOGY,
    ENTITY_TYPES,
    ENTITY_UI_ELEMENT,
    ENTITY_USER_FLOW,
    HAS_CONTROL,
    HAS_FIELD,
    HAS_FORM,
    IMPLEMENTED_BY,
    INFERRED,
    KNOWLEDGE_MODEL_VERSION,
    LIKELY_TRIGGERS,
    NAVIGATES_TO,
    OBSERVATION_STATUSES,
    OBSERVED,
    OBSERVED_ON,
    PART_OF_FLOW,
    RELATIONSHIP_TYPES,
    SATISFIED_BY,
    SATISFIES,
    STARTS_AT,
    SUBMITS_TO,
    UNKNOWN,
    USES,
    ApplicationKnowledgeModel,
    IdCandidate,
    KnowledgeEntity,
    KnowledgeProvenance,
    KnowledgeRelationship,
    allocate_ids,
    normalize_path,
    relationship_id,
    short_hash,
    slugify,
    weakest_status,
)
from agentqe.knowledge.serialization import (
    deterministic_fingerprint,
    from_dict,
    from_json,
    strip_volatile,
    structural_fingerprint,
    to_dict,
    to_json,
)
from agentqe.knowledge.validators import CHECKS, validate_knowledge_model

__all__ = [
    # interfaces
    "ApplicationKnowledgeBuilder",
    "ApplicationKnowledgeQuery",
    "KnowledgeModelError",
    "KnowledgeBuildError",
    # builder
    "DeterministicApplicationKnowledgeBuilder",
    "KnowledgeLimits",
    # query / graph / index
    "DeterministicKnowledgeQuery",
    "DEFAULT_RESULT_LIMIT",
    "KnowledgeIndex",
    "KnowledgeGraph",
    "GraphEdge",
    "build_summaries",
    # validation
    "validate_knowledge_model",
    "CHECKS",
    # serialization
    "to_dict",
    "from_dict",
    "to_json",
    "from_json",
    "strip_volatile",
    "deterministic_fingerprint",
    "structural_fingerprint",
    # schemas
    "ApplicationKnowledgeModel",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "KnowledgeProvenance",
    "IdCandidate",
    "allocate_ids",
    "relationship_id",
    "slugify",
    "short_hash",
    "normalize_path",
    "weakest_status",
    "KNOWLEDGE_MODEL_VERSION",
    # entity vocabulary
    "ENTITY_TYPES",
    "ENTITY_ID_PREFIXES",
    "ENTITY_APPLICATION",
    "ENTITY_MODULE",
    "ENTITY_PAGE",
    "ENTITY_CONTROL",
    "ENTITY_FORM",
    "ENTITY_API_ENDPOINT",
    "ENTITY_USER_FLOW",
    "ENTITY_REQUIREMENT",
    "ENTITY_REPOSITORY_FILE",
    "ENTITY_REPOSITORY_SYMBOL",
    "ENTITY_TECHNOLOGY",
    "ENTITY_UI_ELEMENT",
    # relationship vocabulary
    "RELATIONSHIP_TYPES",
    "CONTAINS",
    "BELONGS_TO",
    "HAS_FIELD",
    "HAS_CONTROL",
    "HAS_FORM",
    "USES",
    "CALLS",
    "SUBMITS_TO",
    "LIKELY_TRIGGERS",
    "NAVIGATES_TO",
    "SATISFIES",
    "SATISFIED_BY",
    "IMPLEMENTED_BY",
    "OBSERVED_ON",
    "ASSOCIATED_WITH",
    "DEPENDS_ON",
    "PART_OF_FLOW",
    "STARTS_AT",
    # derivation + status vocabulary
    "DERIVATION_KINDS",
    "DERIVATION_TRANSLATED",
    "DERIVATION_STRUCTURAL",
    "OBSERVED",
    "INFERRED",
    "UNKNOWN",
    "OBSERVATION_STATUSES",
]
