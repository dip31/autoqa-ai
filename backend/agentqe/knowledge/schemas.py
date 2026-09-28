"""
Phase 1.5G — Application Knowledge Model schemas.

Where Phase 1.5F (``agentqe.fusion``) answers *"what evidence did we collect and
how do the evidence sources correlate?"*, Phase 1.5G answers *"what does this
application contain and how are its concepts related?"*.

The knowledge model is therefore **not** a rename of ``UnifiedApplicationModel``.
It is a second, semantic layer that:

* names things the way a human would (``page:login``, ``control:sign_in``)
  instead of by fusion sequence number (``page_001``, ``control_007``);
* expresses a single controlled relationship vocabulary over a uniform
  ``KnowledgeEntity`` / ``KnowledgeRelationship`` pair, so consumers never have
  to know which collection an item came from;
* keeps a hard link back to the unified model (``source_entity_id``) and to the
  raw evidence (``evidence_refs``), so every node can answer *"where did this
  come from?"* and every edge can answer *"why does this exist?"*.

Honesty rules inherited from Phase 1.5F and enforced here
---------------------------------------------------------
1. ``status`` is ``observed`` / ``inferred`` / ``unknown`` and is **never
   upgraded**. An inferred control stays inferred in the knowledge model.
2. ``confidence`` is copied verbatim. ``None`` stays ``None`` — the knowledge
   layer is not permitted to manufacture certainty.
3. Nothing is inferred from name similarity alone. Every relationship is either
   a translation of a Phase 1.5F relationship (``source_relationship_id`` set)
   or a structural consequence of a Phase 1.5F membership list
   (``derivation`` set). Both are recorded.
4. No raw DOM, no screenshots, no network bodies, no credentials. Only
   references.

This module has no dependency on OmniParser, Playwright, Flask, any LLM
provider, LlamaIndex, LangGraph, a vector store, or a graph database.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Versioning (§35)
# ---------------------------------------------------------------------------

#: Schema version of the knowledge model itself. Bump only on a breaking
#: change to the serialized shape, so that ``from_dict`` can migrate.
KNOWLEDGE_MODEL_VERSION = "1.0"

#: Name of the reference builder implementation (recorded in provenance).
DEFAULT_BUILDER_NAME = "DeterministicApplicationKnowledgeBuilder"

#: The upstream model this knowledge layer is derived from.
SOURCE_MODEL_NAME = "UnifiedApplicationModel"


# ---------------------------------------------------------------------------
# Observation status (§32) — identical vocabulary to Phase 1.5F on purpose
# ---------------------------------------------------------------------------

OBSERVED = "observed"
INFERRED = "inferred"
UNKNOWN = "unknown"

OBSERVATION_STATUSES = (OBSERVED, INFERRED, UNKNOWN)

#: Ordered weakest-last. Used when a derived edge must not claim more certainty
#: than the weakest thing it depends on.
_STATUS_STRENGTH = {OBSERVED: 2, INFERRED: 1, UNKNOWN: 0}


def weakest_status(*statuses: Optional[str]) -> str:
    """
    Return the least-certain of ``statuses``.

    Used for structural edges: an edge derived from an inferred module can never
    be stronger than ``inferred``. Unrecognised values are treated as
    ``unknown`` so an unexpected input degrades safely rather than inflating
    certainty.
    """
    strengths = [_STATUS_STRENGTH.get(s, 0) for s in statuses if s is not None]
    if not strengths:
        return UNKNOWN
    minimum = min(strengths)
    for name, value in _STATUS_STRENGTH.items():
        if value == minimum:
            return name
    return UNKNOWN


# ---------------------------------------------------------------------------
# Entity types (§7)
# ---------------------------------------------------------------------------

ENTITY_APPLICATION = "application"
ENTITY_MODULE = "module"
ENTITY_PAGE = "page"
ENTITY_CONTROL = "control"
ENTITY_FORM = "form"
ENTITY_API_ENDPOINT = "api_endpoint"
ENTITY_USER_FLOW = "user_flow"
ENTITY_REQUIREMENT = "requirement"
ENTITY_REPOSITORY_FILE = "repository_file"
ENTITY_REPOSITORY_SYMBOL = "repository_symbol"
ENTITY_TECHNOLOGY = "technology"
ENTITY_UI_ELEMENT = "ui_element"

ENTITY_TYPES = (
    ENTITY_APPLICATION,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_API_ENDPOINT,
    ENTITY_USER_FLOW,
    ENTITY_REQUIREMENT,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REPOSITORY_SYMBOL,
    ENTITY_TECHNOLOGY,
    ENTITY_UI_ELEMENT,
)

#: ``ui_element`` is part of the supported vocabulary but the deterministic
#: builder does not emit it: Phase 1.5F already promotes every visual-only
#: OmniParser element into a ``UnifiedControl``, so a separate ``ui_element``
#: node would duplicate an existing ``control`` node rather than add knowledge.
#: The type is reserved for a future phase that observes non-interactive UI.
ENTITY_TYPES_NOT_EMITTED = (ENTITY_UI_ELEMENT,)

#: Stable id prefix per entity type (§8). Deliberately human-readable.
ENTITY_ID_PREFIXES: Dict[str, str] = {
    ENTITY_APPLICATION: "application",
    ENTITY_MODULE: "module",
    ENTITY_PAGE: "page",
    ENTITY_CONTROL: "control",
    ENTITY_FORM: "form",
    ENTITY_API_ENDPOINT: "api",
    ENTITY_USER_FLOW: "flow",
    ENTITY_REQUIREMENT: "requirement",
    ENTITY_REPOSITORY_FILE: "repo:file",
    ENTITY_REPOSITORY_SYMBOL: "repo:symbol",
    ENTITY_TECHNOLOGY: "technology",
    ENTITY_UI_ELEMENT: "ui",
}


# ---------------------------------------------------------------------------
# Relationship vocabulary (§21)
# ---------------------------------------------------------------------------
#
# CASE POLICY: relationship values are stored **lower_snake_case** throughout
# the implementation, matching both the concrete JSON example in §20
# (``"relationship": "likely_triggers"``) and the Phase 1.5F vocabulary. The
# uppercase spelling used in the specification prose (``LIKELY_TRIGGERS``) is a
# display convention only; the frontend upper-cases for presentation.

CONTAINS = "contains"
BELONGS_TO = "belongs_to"
HAS_FIELD = "has_field"
HAS_CONTROL = "has_control"
HAS_FORM = "has_form"
USES = "uses"
CALLS = "calls"
SUBMITS_TO = "submits_to"
LIKELY_TRIGGERS = "likely_triggers"
NAVIGATES_TO = "navigates_to"
SATISFIES = "satisfies"
SATISFIED_BY = "satisfied_by"
IMPLEMENTED_BY = "implemented_by"
OBSERVED_ON = "observed_on"
ASSOCIATED_WITH = "associated_with"
DEPENDS_ON = "depends_on"
PART_OF_FLOW = "part_of_flow"
STARTS_AT = "starts_at"

RELATIONSHIP_TYPES = (
    CONTAINS,
    BELONGS_TO,
    HAS_FIELD,
    HAS_CONTROL,
    HAS_FORM,
    USES,
    CALLS,
    SUBMITS_TO,
    LIKELY_TRIGGERS,
    NAVIGATES_TO,
    SATISFIES,
    SATISFIED_BY,
    IMPLEMENTED_BY,
    OBSERVED_ON,
    ASSOCIATED_WITH,
    DEPENDS_ON,
    PART_OF_FLOW,
    STARTS_AT,
)

#: Relationships the deterministic builder never emits, kept in the vocabulary
#: so later phases (and a future graph database) can use them without a schema
#: change. Documented rather than silently absent.
#:
#: ``satisfied_by``  — the inverse of ``satisfies``. Only one direction is
#:                     stored to avoid doubling the edge count; the query layer
#:                     resolves the inverse from incoming edges.
#: ``depends_on``    — Phase 1.5F establishes no dependency evidence.
#: ``part_of_flow``  — flow membership is stored as ``flow --uses--> control``
#:                     per §16 rather than as a second inverse edge.
RELATIONSHIP_TYPES_NOT_EMITTED = (SATISFIED_BY, DEPENDS_ON, PART_OF_FLOW)

#: How a relationship came to exist. Every edge carries exactly one.
#:   ``translated``  — a Phase 1.5F ``Relationship`` re-expressed in knowledge
#:                     ids and vocabulary. ``source_relationship_id`` is set.
#:   ``structural``  — a direct consequence of a Phase 1.5F membership list
#:                     (e.g. ``UnifiedPage.controls``). ``derivation`` explains
#:                     which list.
DERIVATION_TRANSLATED = "translated"
DERIVATION_STRUCTURAL = "structural"
DERIVATION_KINDS = (DERIVATION_TRANSLATED, DERIVATION_STRUCTURAL)


# ---------------------------------------------------------------------------
# Naming helpers (§9)
# ---------------------------------------------------------------------------

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_MULTI_UNDERSCORE_RE = re.compile(r"_{2,}")

#: Slugs longer than this are truncated; collisions caused by truncation are
#: resolved by the tiered allocator below, so truncation is always safe.
MAX_SLUG_LENGTH = 60


def slugify(value: Any, max_length: int = MAX_SLUG_LENGTH, fallback: str = "") -> str:
    """
    Produce a canonical, lower_snake_case key from a user-facing string.

    ``"Sign In"`` -> ``"sign_in"``. The original casing is *never* destroyed —
    it is preserved separately on ``KnowledgeEntity.display_name`` (§9).
    """
    if value is None:
        return fallback
    text = str(value).strip().lower()
    text = _SLUG_STRIP_RE.sub("_", text)
    text = _MULTI_UNDERSCORE_RE.sub("_", text).strip("_")
    if not text:
        return fallback
    if len(text) > max_length:
        text = text[:max_length].rstrip("_")
    return text or fallback


def short_hash(value: str, length: int = 8) -> str:
    """Deterministic, stable, platform-independent short digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def normalize_path(path: Any) -> str:
    """Normalize a repository path for use inside an id (§18)."""
    text = str(path or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.strip("/")


# ---------------------------------------------------------------------------
# Deterministic id allocation (§8)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IdCandidate:
    """
    A request for a deterministic entity id.

    ``key``   A stable identity string that is unique for this entity across
              the whole build (normally the Phase 1.5F ``source_entity_id``
              plus its distinguishing attributes). It is hashed, never shown.
    ``tiers`` Progressively more-qualified id candidates, most readable first,
              e.g. ``("control:sign_in", "control:login_sign_in")``.
    """
    key: str
    tiers: Tuple[str, ...]


def allocate_ids(candidates: Sequence[IdCandidate]) -> Dict[str, str]:
    """
    Assign a unique id to every candidate, deterministically and **independently
    of iteration order**.

    Why order-independence matters: §52 requires that rebuilding from the same
    unified model yields identical ids, and Phase 2 will cache embeddings keyed
    by these ids. A naive "append ``_2`` to whoever comes second" scheme would
    make ids depend on list order and on unrelated entities appearing earlier.

    Algorithm — for each tier, in order:
      * group the still-unassigned candidates by their id at that tier;
      * a group of exactly one whose id is not already taken wins that id;
      * every other candidate falls through to the next tier.
    Anything still unassigned after the last tier gets
    ``<last tier>__<sha256(key)[:8]>``, which is a pure function of the
    candidate's own identity and therefore order-independent too.

    Returns:
        ``{candidate.key: allocated_id}``.
    """
    assigned: Dict[str, str] = {}
    taken: set = set()
    pending: List[IdCandidate] = list(candidates)

    if not pending:
        return assigned

    max_tiers = max(len(c.tiers) for c in pending) if pending else 0

    for tier_index in range(max_tiers):
        if not pending:
            break
        groups: Dict[str, List[IdCandidate]] = {}
        for candidate in pending:
            tier_id = candidate.tiers[min(tier_index, len(candidate.tiers) - 1)]
            groups.setdefault(tier_id, []).append(candidate)

        still_pending: List[IdCandidate] = []
        # Sorting the group keys keeps the *traversal* deterministic; the
        # outcome is already order-independent because a group only wins when
        # it is a singleton.
        for tier_id in sorted(groups):
            members = groups[tier_id]
            if len(members) == 1 and tier_id not in taken:
                assigned[members[0].key] = tier_id
                taken.add(tier_id)
            else:
                still_pending.extend(members)
        pending = still_pending

    # Residual collisions: disambiguate by the candidate's own identity hash.
    for candidate in sorted(pending, key=lambda c: c.key):
        base = candidate.tiers[-1] if candidate.tiers else "entity"
        entity_id = f"{base}__{short_hash(candidate.key)}"
        # Duplicate keys would be a builder bug; fall back to a full digest
        # rather than silently overwriting an id.
        if entity_id in taken:
            entity_id = f"{base}__{short_hash(candidate.key, 32)}"
        assigned[candidate.key] = entity_id
        taken.add(entity_id)

    return assigned


def relationship_id(source_id: str, relationship: str, target_id: str) -> str:
    """
    Deterministic relationship id (§20).

    Shape: ``relationship:<source>:<relationship>:<target>``, e.g.
    ``relationship:control:sign_in:likely_triggers:api:post:/api/auth/login``.

    Entity ids already contain ``:``, so the result contains more than four
    segments. That is intentional: the id stays directly readable, and
    uniqueness comes from the (source, relationship, target) triple being
    unique by construction — the builder merges duplicates before emitting.
    """
    return f"relationship:{source_id}:{relationship}:{target_id}"


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntity:
    """
    One node of the semantic application graph (§7).

    Provenance fields — all four answer "where did this come from?" (§23):
      ``source_entity_id``   the Phase 1.5F id (``control_007``) this was built
                             from, or ``None`` for entities the knowledge layer
                             introduces (``application``, ``technology``,
                             ``repository_file``).
      ``source_entity_type`` which Phase 1.5F collection it came from.
      ``evidence_refs``      raw-evidence references, copied verbatim from
                             Phase 1.5F (``dom:page_001:element_005`` ...).
      ``requirement_refs`` / ``repository_refs`` carried over unchanged.
    """
    id: str
    entity_type: str
    name: str = ""
    display_name: str = ""
    canonical_name: str = ""
    description: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    # Provenance / traceability
    source_entity_id: Optional[str] = None
    source_entity_type: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    repository_refs: List[Dict[str, Any]] = field(default_factory=list)

    # Honesty (§32, §33)
    status: str = OBSERVED
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    inference_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "display_name": self.display_name,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "properties": self.properties,
            "source_entity_id": self.source_entity_id,
            "source_entity_type": self.source_entity_type,
            "evidence_refs": list(self.evidence_refs),
            "evidence_sources": list(self.evidence_sources),
            "requirement_refs": list(self.requirement_refs),
            "repository_refs": [dict(r) for r in self.repository_refs],
            "status": self.status,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "inference_reason": self.inference_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEntity":
        return cls(
            id=data.get("id", ""),
            entity_type=data.get("entity_type", ""),
            name=data.get("name", "") or "",
            display_name=data.get("display_name", "") or "",
            canonical_name=data.get("canonical_name", "") or "",
            description=data.get("description"),
            properties=dict(data.get("properties") or {}),
            source_entity_id=data.get("source_entity_id"),
            source_entity_type=data.get("source_entity_type"),
            evidence_refs=list(data.get("evidence_refs") or []),
            evidence_sources=list(data.get("evidence_sources") or []),
            requirement_refs=list(data.get("requirement_refs") or []),
            repository_refs=[dict(r) for r in (data.get("repository_refs") or [])],
            status=data.get("status", OBSERVED),
            confidence=data.get("confidence"),
            confidence_basis=data.get("confidence_basis"),
            inference_reason=data.get("inference_reason"),
        )


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeRelationship:
    """
    One edge of the semantic application graph (§20).

    Every edge answers "why does this relationship exist?" (§23) through
    exactly one of:
      * ``source_relationship_id`` — it is a translation of a Phase 1.5F
        relationship, whose status / confidence / reason are carried over; or
      * ``derivation`` — it is a structural consequence of a Phase 1.5F
        membership list, named explicitly (``"UnifiedPage.controls"``).
    """
    id: str
    source_id: str
    relationship: str
    target_id: str
    status: str = INFERRED
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    inference_reason: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)

    # Provenance
    source_relationship_id: Optional[str] = None
    derivation_kind: str = DERIVATION_STRUCTURAL
    derivation: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "relationship": self.relationship,
            "target_id": self.target_id,
            "status": self.status,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "inference_reason": self.inference_reason,
            "evidence_refs": list(self.evidence_refs),
            "source_relationship_id": self.source_relationship_id,
            "derivation_kind": self.derivation_kind,
            "derivation": self.derivation,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeRelationship":
        return cls(
            id=data.get("id", ""),
            source_id=data.get("source_id", ""),
            relationship=data.get("relationship", ASSOCIATED_WITH),
            target_id=data.get("target_id", ""),
            status=data.get("status", INFERRED),
            confidence=data.get("confidence"),
            confidence_basis=data.get("confidence_basis"),
            inference_reason=data.get("inference_reason"),
            evidence_refs=list(data.get("evidence_refs") or []),
            source_relationship_id=data.get("source_relationship_id"),
            derivation_kind=data.get("derivation_kind", DERIVATION_STRUCTURAL),
            derivation=data.get("derivation"),
            properties=dict(data.get("properties") or {}),
        )


# ---------------------------------------------------------------------------
# Provenance (§34)
# ---------------------------------------------------------------------------

#: Fields that legitimately differ between two builds of the same input.
#: ``deterministic_fingerprint`` (serialization.py) strips these before
#: comparing, which is what makes the §52 repeated-build test meaningful
#: instead of trivially failing on a clock tick.
VOLATILE_PROVENANCE_FIELDS = ("generated_at", "duration_ms")


@dataclass
class KnowledgeProvenance:
    """Where this knowledge model came from and how it was produced."""
    source_model: str = SOURCE_MODEL_NAME
    fusion_version: Optional[str] = None
    fusion_timestamp: Optional[str] = None
    fusion_engine: Optional[str] = None
    knowledge_model_version: str = KNOWLEDGE_MODEL_VERSION
    generated_at: str = ""
    builder: str = DEFAULT_BUILDER_NAME
    llm_used: bool = False
    duration_ms: Optional[float] = None
    evidence_sources: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_model": self.source_model,
            "fusion_version": self.fusion_version,
            "fusion_timestamp": self.fusion_timestamp,
            "fusion_engine": self.fusion_engine,
            "knowledge_model_version": self.knowledge_model_version,
            "generated_at": self.generated_at,
            "builder": self.builder,
            "llm_used": self.llm_used,
            "duration_ms": self.duration_ms,
            "evidence_sources": list(self.evidence_sources),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeProvenance":
        data = data or {}
        return cls(
            source_model=data.get("source_model", SOURCE_MODEL_NAME),
            fusion_version=data.get("fusion_version"),
            fusion_timestamp=data.get("fusion_timestamp"),
            fusion_engine=data.get("fusion_engine"),
            knowledge_model_version=data.get("knowledge_model_version", KNOWLEDGE_MODEL_VERSION),
            generated_at=data.get("generated_at", "") or "",
            builder=data.get("builder", DEFAULT_BUILDER_NAME),
            llm_used=bool(data.get("llm_used", False)),
            duration_ms=data.get("duration_ms"),
            evidence_sources=list(data.get("evidence_sources") or []),
            warnings=list(data.get("warnings") or []),
        )


# ---------------------------------------------------------------------------
# Top-level model (§6)
# ---------------------------------------------------------------------------

@dataclass
class ApplicationKnowledgeModel:
    """
    The structured, queryable semantic layer over ``UnifiedApplicationModel``.

    Serialized shape::

        {
            "model_version": "1.0",
            "application": {...},       # denormalized application entity summary
            "entities": [...],          # KnowledgeEntity
            "relationships": [...],     # KnowledgeRelationship
            "indexes": {...},           # deterministic lookup tables
            "summaries": {...},         # counts derived from the data itself
            "provenance": {...},
            "metadata": {...}
        }

    ``indexes`` are *derived* data. They are serialized so a consumer can load a
    model and query it without rebuilding, and ``from_dict`` rebuilds them when
    they are absent, so the model is never dependent on them being correct on
    disk.
    """
    model_version: str = KNOWLEDGE_MODEL_VERSION
    application: Dict[str, Any] = field(default_factory=dict)
    entities: List[KnowledgeEntity] = field(default_factory=list)
    relationships: List[KnowledgeRelationship] = field(default_factory=list)
    indexes: Dict[str, Any] = field(default_factory=dict)
    summaries: Dict[str, Any] = field(default_factory=dict)
    provenance: KnowledgeProvenance = field(default_factory=KnowledgeProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # -- convenience lookups (not serialized) -------------------------------

    def entity_by_id(self, entity_id: str) -> Optional[KnowledgeEntity]:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        return None

    def entities_of_type(self, entity_type: str) -> List[KnowledgeEntity]:
        return [e for e in self.entities if e.entity_type == entity_type]

    def entity_ids(self) -> set:
        return {e.id for e in self.entities}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_version": self.model_version,
            "application": self.application,
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
            "indexes": self.indexes,
            "summaries": self.summaries,
            "provenance": self.provenance.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApplicationKnowledgeModel":
        data = data or {}
        return cls(
            model_version=data.get("model_version", KNOWLEDGE_MODEL_VERSION),
            application=dict(data.get("application") or {}),
            entities=[KnowledgeEntity.from_dict(e) for e in (data.get("entities") or [])],
            relationships=[
                KnowledgeRelationship.from_dict(r) for r in (data.get("relationships") or [])
            ],
            indexes=dict(data.get("indexes") or {}),
            summaries=dict(data.get("summaries") or {}),
            provenance=KnowledgeProvenance.from_dict(data.get("provenance") or {}),
            metadata=dict(data.get("metadata") or {}),
        )


__all__ = [
    "KNOWLEDGE_MODEL_VERSION",
    "DEFAULT_BUILDER_NAME",
    "SOURCE_MODEL_NAME",
    "OBSERVED",
    "INFERRED",
    "UNKNOWN",
    "OBSERVATION_STATUSES",
    "weakest_status",
    "ENTITY_TYPES",
    "ENTITY_TYPES_NOT_EMITTED",
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
    "RELATIONSHIP_TYPES",
    "RELATIONSHIP_TYPES_NOT_EMITTED",
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
    "DERIVATION_TRANSLATED",
    "DERIVATION_STRUCTURAL",
    "DERIVATION_KINDS",
    "slugify",
    "short_hash",
    "normalize_path",
    "MAX_SLUG_LENGTH",
    "IdCandidate",
    "allocate_ids",
    "relationship_id",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "KnowledgeProvenance",
    "ApplicationKnowledgeModel",
    "VOLATILE_PROVENANCE_FIELDS",
]
