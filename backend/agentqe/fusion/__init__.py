"""
Phase 1.5F — Cross-modal evidence fusion package.

Turns the evidence collected by Phases 1.5A–1.5E (crawl, DOM, accessibility,
network, screenshots, OmniParser visual UI) plus requirement and repository
analysis into a single traceable ``UnifiedApplicationModel``.

The raw evidence is never replaced: the unified model only *references* it
through stable evidence-reference strings such as ``dom:page_001:element_005``.

Typical use::

    from agentqe.fusion import DeterministicEvidenceFusionEngine, validate_unified_model

    engine = DeterministicEvidenceFusionEngine()
    model = engine.fuse(application_context)
    report = validate_unified_model(model)
    model.fusion_metadata.validation = report
    application_context.unified_model = model.to_dict()

This phase is deliberately deterministic: no LLM, no embeddings, no vector
store, no network access. ``EvidenceFusionEngine`` is the seam a future
semantic engine can implement.
"""

from agentqe.fusion.confidence import (
    UI_API_SIGNAL_WEIGHTS,
    clamp_confidence,
    correlation_confidence,
    flow_confidence,
    ui_api_confidence,
)
from agentqe.fusion.correlators import (
    AX_DOM_MATCH_THRESHOLD,
    VISUAL_DOM_AMBIGUITY_MARGIN,
    VISUAL_DOM_MATCH_THRESHOLD,
    bbox_iou,
    correlate_ax_to_dom,
    correlate_visual_to_dom,
    flatten_ax_tree,
    role_compatibility,
    text_similarity,
)
from agentqe.fusion.evidence_fusion import (
    DeterministicEvidenceFusionEngine,
    FusionLimits,
)
from agentqe.fusion.interfaces import EvidenceFusionEngine, EvidenceFusionError
from agentqe.fusion.schemas import (
    CONTROL_TYPES,
    EVIDENCE_REF_KINDS,
    EVIDENCE_SOURCES,
    FUSION_VERSION,
    INFERRED,
    OBSERVATION_STATUSES,
    OBSERVED,
    RELATIONSHIP_TYPES,
    SEMANTIC_ROLES,
    UNKNOWN,
    FusionMetadata,
    Relationship,
    UnifiedAPIEndpoint,
    UnifiedApplicationModel,
    UnifiedControl,
    UnifiedForm,
    UnifiedModule,
    UnifiedPage,
    UnifiedRequirement,
    UnifiedUserFlow,
    UserFlowStep,
    evidence_ref,
)
from agentqe.fusion.validators import validate_unified_model

__all__ = [
    # interfaces
    "EvidenceFusionEngine",
    "EvidenceFusionError",
    # engine
    "DeterministicEvidenceFusionEngine",
    "FusionLimits",
    # validation
    "validate_unified_model",
    # schemas
    "UnifiedApplicationModel",
    "UnifiedPage",
    "UnifiedControl",
    "UnifiedForm",
    "UnifiedAPIEndpoint",
    "UnifiedUserFlow",
    "UserFlowStep",
    "UnifiedModule",
    "UnifiedRequirement",
    "Relationship",
    "FusionMetadata",
    "evidence_ref",
    # vocabularies
    "OBSERVED",
    "INFERRED",
    "UNKNOWN",
    "OBSERVATION_STATUSES",
    "CONTROL_TYPES",
    "RELATIONSHIP_TYPES",
    "SEMANTIC_ROLES",
    "EVIDENCE_SOURCES",
    "EVIDENCE_REF_KINDS",
    "FUSION_VERSION",
    # correlation / confidence helpers (useful for tests and future engines)
    "text_similarity",
    "bbox_iou",
    "role_compatibility",
    "flatten_ax_tree",
    "correlate_ax_to_dom",
    "correlate_visual_to_dom",
    "VISUAL_DOM_MATCH_THRESHOLD",
    "VISUAL_DOM_AMBIGUITY_MARGIN",
    "AX_DOM_MATCH_THRESHOLD",
    "clamp_confidence",
    "correlation_confidence",
    "ui_api_confidence",
    "flow_confidence",
    "UI_API_SIGNAL_WEIGHTS",
]
