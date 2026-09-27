"""
Phase 1.5F — Unified Application Model schemas.

These dataclasses describe the *fused interpretation* of evidence already
collected by earlier phases (1.5A crawl, 1.5B DOM/AX, 1.5C network,
1.5D screenshots, 1.5E visual UI) plus requirement/repository analysis.

Design rules enforced by these schemas
--------------------------------------
1. TRACEABILITY — every entity carries ``evidence_refs`` pointing back at the
   raw evidence inside ApplicationContext. The unified model never *replaces*
   raw evidence; it references it.
2. NO OVER-INFERENCE — every entity carries an ``observation_status`` of
   ``observed`` / ``inferred`` / ``unknown``, and any inference carries an
   ``inference_reason``. Semantic roles are ``None`` when unsupported.
3. NO FABRICATED CONFIDENCE — ``confidence`` is ``None`` unless a documented
   formula produced it, in which case ``confidence_basis`` explains how.
4. NO BULK DUPLICATION — raw DOM trees / AX trees / screenshots are never
   copied here. Only stable string references are stored.

Plain dataclasses are used to stay consistent with the rest of AgentQE
(``agentqe.models.context``, ``agentqe.vision.schemas``) and to avoid adding a
new framework dependency.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

#: Directly supported by collected evidence.
OBSERVED = "observed"
#: Derived from multiple evidence sources or a deterministic relationship.
INFERRED = "inferred"
#: Insufficient evidence to characterise the entity.
UNKNOWN = "unknown"

OBSERVATION_STATUSES = (OBSERVED, INFERRED, UNKNOWN)

#: Control types the fusion layer is allowed to emit. Anything that cannot be
#: supported by evidence becomes ``"other"`` (never a guessed specific type).
CONTROL_TYPES = (
    "button",
    "input",
    "checkbox",
    "radio",
    "link",
    "dropdown",
    "select",
    "menu",
    "tab",
    "textarea",
    "icon",
    "other",
)

#: Relationship vocabulary. Intentionally small.
RELATIONSHIP_TYPES = (
    "contains",
    "belongs_to",
    "labels",
    "associated_with",
    "likely_triggers",
    "submits_to",
    "navigates_to",
    "rendered_on",
    "implements",
    "satisfies",
    "observed_with",
)

#: Semantic roles the deterministic engine may infer. Kept deliberately narrow.
SEMANTIC_ROLES = (
    "authentication_submit",
    "authentication_username",
    "authentication_password",
    "authentication",
    "search_input",
    "search_submit",
    "search",
    "form_submit",
    "navigation_link",
)

EVIDENCE_SOURCES = (
    "requirements",
    "repository",
    "dom",
    "accessibility",
    "network",
    "screenshot",
    "visual_ui",
    "crawl",
)

#: Allowed *prefixes* of an ``evidence_ref`` string. These are reference kinds
#: (how to find the raw evidence), which is not quite the same list as
#: ``EVIDENCE_SOURCES`` (which names the modality):
#:   ``crawl``       -> ApplicationContext.pages[i]                (CrawledPage)
#:   ``dom``         -> ...pages[i].dom.interactive_elements / .forms
#:   ``ax``          -> ...pages[i].accessibility_tree (flattened node index)
#:   ``visual``      -> ...pages[i].visual_ui.elements
#:   ``network``     -> ...pages[i].network_activity[j]
#:   ``screenshot``  -> ...pages[i].screenshot (artifact metadata only)
#:   ``requirement`` -> a normalized UnifiedRequirement id
#:   ``repository``  -> a normalized repository source entry
#:   ``context``     -> a named ApplicationContext field produced by an earlier
#:                      phase (e.g. ``context:modules:2``) for evidence that is
#:                      not page-scoped
EVIDENCE_REF_KINDS = (
    "crawl",
    "dom",
    "ax",
    "visual",
    "network",
    "screenshot",
    "requirement",
    "repository",
    "context",
)

FUSION_VERSION = "1.0"


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``d`` unchanged. Hook kept for future pruning policies."""
    return d


# ---------------------------------------------------------------------------
# Evidence reference helpers
# ---------------------------------------------------------------------------

def evidence_ref(kind: str, *parts: str) -> str:
    """
    Build a stable evidence reference string.

    Examples::

        evidence_ref("dom", "page_001", "element_005")  -> "dom:page_001:element_005"
        evidence_ref("requirement", "REQ-002")          -> "requirement:REQ-002"
    """
    tokens = [kind] + [str(p) for p in parts if p is not None and str(p) != ""]
    return ":".join(tokens)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

@dataclass
class UnifiedControl:
    """
    A single interactive UI control, fused from any combination of
    DOM, accessibility, and visual evidence.

    ``observation_status`` describes the entity *as asserted here*:
      - ``observed``  : every asserted attribute comes straight from evidence.
      - ``inferred``  : at least one asserted attribute (e.g. ``semantic_role``
                        or a cross-modal merge) was derived.
      - ``unknown``   : the control was detected but could not be characterised.

    ``semantic_role_status`` is never ``observed`` — a semantic role is always an
    interpretation, so it is ``inferred`` or ``unknown``.
    """
    id: str
    type: str = "other"
    label: Optional[str] = None
    text: Optional[str] = None
    semantic_role: Optional[str] = None
    semantic_role_status: str = UNKNOWN
    observation_status: str = OBSERVED
    interactable: Optional[bool] = None
    page_id: str = ""

    # References into raw evidence (never inlined copies)
    dom_ref: Optional[str] = None
    accessibility_ref: Optional[str] = None
    visual_ref: Optional[str] = None

    # Geometry
    bbox_pixels: Optional[List[float]] = None
    bbox_normalized: Optional[List[float]] = None

    # Identity hints carried over from the DOM (useful for later phases)
    dom_id: Optional[str] = None
    dom_tag: Optional[str] = None
    dom_name: Optional[str] = None
    dom_type: Optional[str] = None
    role: Optional[str] = None
    href: Optional[str] = None
    form_id: Optional[str] = None

    # Provenance / explainability
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    inference_reason: Optional[str] = None
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    correlation: Dict[str, Any] = field(default_factory=dict)

    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "text": self.text,
            "semantic_role": self.semantic_role,
            "semantic_role_status": self.semantic_role_status,
            "observation_status": self.observation_status,
            "interactable": self.interactable,
            "page_id": self.page_id,
            "dom_ref": self.dom_ref,
            "accessibility_ref": self.accessibility_ref,
            "visual_ref": self.visual_ref,
            "bbox_pixels": self.bbox_pixels,
            "bbox_normalized": self.bbox_normalized,
            "dom_id": self.dom_id,
            "dom_tag": self.dom_tag,
            "dom_name": self.dom_name,
            "dom_type": self.dom_type,
            "role": self.role,
            "href": self.href,
            "form_id": self.form_id,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "inference_reason": self.inference_reason,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "correlation": self.correlation,
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": list(self.repository_refs),
        })


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

@dataclass
class UnifiedForm:
    """A form fused from DOM structure, accessibility labels, controls and
    (where observed) network activity."""
    id: str
    page_id: str = ""
    name: Optional[str] = None
    action: Optional[str] = None
    method: Optional[str] = None
    fields: List[str] = field(default_factory=list)          # control ids
    submit_control: Optional[str] = None                     # control id
    observed_api_endpoints: List[str] = field(default_factory=list)  # api ids
    semantic_role: Optional[str] = None
    semantic_role_status: str = UNKNOWN
    observation_status: str = OBSERVED
    dom_ref: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    inference_reason: Optional[str] = None
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "page_id": self.page_id,
            "name": self.name,
            "action": self.action,
            "method": self.method,
            "fields": list(self.fields),
            "submit_control": self.submit_control,
            "observed_api_endpoints": list(self.observed_api_endpoints),
            "semantic_role": self.semantic_role,
            "semantic_role_status": self.semantic_role_status,
            "observation_status": self.observation_status,
            "dom_ref": self.dom_ref,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "inference_reason": self.inference_reason,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": list(self.repository_refs),
        })


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@dataclass
class UnifiedAPIEndpoint:
    """
    A normalized API endpoint observed in network evidence (Phase 1.5C).

    SECURITY: no headers, cookies, tokens, credentials or bodies are stored
    here — only non-sensitive shape metadata.
    """
    id: str
    method: str = "GET"
    url: str = ""
    path: str = ""
    host: str = ""
    observed_on_pages: List[str] = field(default_factory=list)   # page ids
    request_metadata: Dict[str, Any] = field(default_factory=dict)
    response_metadata: Dict[str, Any] = field(default_factory=dict)
    observation_count: int = 0
    failure_count: int = 0
    observation_status: str = OBSERVED
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "method": self.method,
            "url": self.url,
            "path": self.path,
            "host": self.host,
            "observed_on_pages": list(self.observed_on_pages),
            "request_metadata": self.request_metadata,
            "response_metadata": self.response_metadata,
            "observation_count": self.observation_count,
            "failure_count": self.failure_count,
            "observation_status": self.observation_status,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": list(self.repository_refs),
        })


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@dataclass
class UnifiedPage:
    """
    A unified page. References the original CrawledPage (via ``page_index`` and
    ``crawl_ref``) rather than duplicating its DOM / AX / network payloads.
    """
    id: str
    url: str = ""
    normalized_url: str = ""
    title: Optional[str] = None
    page_type: Optional[str] = None
    page_type_status: str = INFERRED
    depth: Optional[int] = None
    crawl_status: str = "unknown"
    observed: bool = True
    observation_status: str = OBSERVED

    page_index: Optional[int] = None      # index into ApplicationContext.pages
    crawl_ref: Optional[str] = None       # "crawl:page_001"
    screenshot_ref: Optional[str] = None  # "screenshot:page_001" (artifact ref only)
    visual_ui_status: Optional[str] = None

    controls: List[str] = field(default_factory=list)
    forms: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)

    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "url": self.url,
            "normalized_url": self.normalized_url,
            "title": self.title,
            "page_type": self.page_type,
            "page_type_status": self.page_type_status,
            "depth": self.depth,
            "crawl_status": self.crawl_status,
            "observed": self.observed,
            "observation_status": self.observation_status,
            "page_index": self.page_index,
            "crawl_ref": self.crawl_ref,
            "screenshot_ref": self.screenshot_ref,
            "visual_ui_status": self.visual_ui_status,
            "controls": list(self.controls),
            "forms": list(self.forms),
            "api_endpoints": list(self.api_endpoints),
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": list(self.repository_refs),
        })


# ---------------------------------------------------------------------------
# User flows
# ---------------------------------------------------------------------------

@dataclass
class UserFlowStep:
    """One step of a user flow. Steps that were not actually executed during the
    crawl are marked ``inferred`` — the crawler does not perform logins."""
    order: int
    action: str                       # navigate | input | click | api_call | observe
    description: str = ""
    page_id: Optional[str] = None
    control_id: Optional[str] = None
    api_endpoint_id: Optional[str] = None
    observation_status: str = INFERRED
    inference_reason: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "order": self.order,
            "action": self.action,
            "description": self.description,
            "page_id": self.page_id,
            "control_id": self.control_id,
            "api_endpoint_id": self.api_endpoint_id,
            "observation_status": self.observation_status,
            "inference_reason": self.inference_reason,
            "evidence_refs": list(self.evidence_refs),
        })


@dataclass
class UnifiedUserFlow:
    id: str
    name: str = ""
    source: str = ""                 # "form_fusion" | "requirement_analysis" | "navigation_graph"
    steps: List[UserFlowStep] = field(default_factory=list)
    page_ids: List[str] = field(default_factory=list)
    control_ids: List[str] = field(default_factory=list)
    api_endpoint_ids: List[str] = field(default_factory=list)
    semantic_role: Optional[str] = None
    observation_status: str = INFERRED
    inference_reason: Optional[str] = None
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "steps": [s.to_dict() for s in self.steps],
            "page_ids": list(self.page_ids),
            "control_ids": list(self.control_ids),
            "api_endpoint_ids": list(self.api_endpoint_ids),
            "semantic_role": self.semantic_role,
            "observation_status": self.observation_status,
            "inference_reason": self.inference_reason,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "requirement_refs": list(self.requirement_refs),
        })


# ---------------------------------------------------------------------------
# Modules & requirements
# ---------------------------------------------------------------------------

@dataclass
class UnifiedModule:
    """
    A module / feature. Names come from evidence that *already named it*
    (crawl-detected flows, requirement analysis, repository analysis).
    The fusion layer never invents a grander name than the evidence supports.
    """
    id: str
    name: str = ""
    source: str = ""                 # crawl | requirement_analysis | repository | features
    pages: List[str] = field(default_factory=list)
    controls: List[str] = field(default_factory=list)
    forms: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    observation_status: str = INFERRED
    inference_reason: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "pages": list(self.pages),
            "controls": list(self.controls),
            "forms": list(self.forms),
            "api_endpoints": list(self.api_endpoints),
            "observation_status": self.observation_status,
            "inference_reason": self.inference_reason,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": list(self.repository_refs),
        })


@dataclass
class UnifiedRequirement:
    """Normalized requirement with a deterministic, stable id (REQ-001, ...)."""
    id: str
    description: str = ""
    source: str = "requirement_analysis"
    keywords: List[str] = field(default_factory=list)
    observation_status: str = OBSERVED   # the requirement text itself is given
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "description": self.description,
            "source": self.source,
            "keywords": list(self.keywords),
            "observation_status": self.observation_status,
            "evidence_refs": list(self.evidence_refs),
        })


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

@dataclass
class Relationship:
    id: str
    source_id: str = ""
    target_id: str = ""
    relationship: str = "associated_with"
    observation_status: str = INFERRED
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    inference_reason: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
            "observation_status": self.observation_status,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "inference_reason": self.inference_reason,
            "evidence_refs": list(self.evidence_refs),
        })


# ---------------------------------------------------------------------------
# Top-level model
# ---------------------------------------------------------------------------

@dataclass
class FusionMetadata:
    fusion_version: str = FUSION_VERSION
    fusion_timestamp: str = ""
    engine: str = "deterministic"
    llm_used: bool = False
    sources: List[str] = field(default_factory=list)
    duration_ms: Optional[float] = None
    limits: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _clean({
            "fusion_version": self.fusion_version,
            "fusion_timestamp": self.fusion_timestamp,
            "engine": self.engine,
            "llm_used": self.llm_used,
            "sources": list(self.sources),
            "duration_ms": self.duration_ms,
            "limits": self.limits,
            "warnings": list(self.warnings),
            "validation": self.validation,
        })


@dataclass
class UnifiedApplicationModel:
    application: Dict[str, Any] = field(default_factory=dict)
    pages: List[UnifiedPage] = field(default_factory=list)
    controls: List[UnifiedControl] = field(default_factory=list)
    forms: List[UnifiedForm] = field(default_factory=list)
    api_endpoints: List[UnifiedAPIEndpoint] = field(default_factory=list)
    user_flows: List[UnifiedUserFlow] = field(default_factory=list)
    modules: List[UnifiedModule] = field(default_factory=list)
    requirements: List[UnifiedRequirement] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    fusion_metadata: FusionMetadata = field(default_factory=FusionMetadata)

    # -- convenience lookups (not serialized) ---------------------------------

    def control_by_id(self, control_id: str) -> Optional[UnifiedControl]:
        for c in self.controls:
            if c.id == control_id:
                return c
        return None

    def page_by_id(self, page_id: str) -> Optional[UnifiedPage]:
        for p in self.pages:
            if p.id == page_id:
                return p
        return None

    def entity_ids(self) -> set:
        ids = set()
        for collection in (
            self.pages, self.controls, self.forms, self.api_endpoints,
            self.user_flows, self.modules, self.requirements,
        ):
            for item in collection:
                ids.add(item.id)
        return ids

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application": self.application,
            "pages": [p.to_dict() for p in self.pages],
            "controls": [c.to_dict() for c in self.controls],
            "forms": [f.to_dict() for f in self.forms],
            "api_endpoints": [a.to_dict() for a in self.api_endpoints],
            "user_flows": [u.to_dict() for u in self.user_flows],
            "modules": [m.to_dict() for m in self.modules],
            "requirements": [r.to_dict() for r in self.requirements],
            "relationships": [r.to_dict() for r in self.relationships],
            "evidence_summary": self.evidence_summary,
            "fusion_metadata": self.fusion_metadata.to_dict(),
        }
