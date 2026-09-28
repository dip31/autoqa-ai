"""
Phase 1.5G — Deterministic Application Knowledge Builder.

Transforms a Phase 1.5F ``UnifiedApplicationModel`` into an
``ApplicationKnowledgeModel``: a semantic graph of application *concepts*
(application / module / page / control / form / api_endpoint / user_flow /
requirement / repository / technology) connected by a controlled relationship
vocabulary.

What this builder is allowed to do
----------------------------------
* Rename Phase 1.5F entities into human-readable, deterministic ids.
* Re-express Phase 1.5F relationships in the knowledge vocabulary, refining
  a generic ``contains`` into ``has_control`` / ``has_form`` / ``has_field``
  based on the *types* of the endpoints. This is a deterministic refinement,
  not an inference.
* Add relationships that are a direct structural consequence of a Phase 1.5F
  membership list (``UnifiedPage.controls``, ``UnifiedModule.pages``,
  ``UnifiedUserFlow.control_ids``, ``*.repository_refs`` ...).

What this builder is forbidden from doing
-----------------------------------------
* Inventing a relationship because two names look similar (§20).
* Upgrading ``inferred`` to ``observed`` (§32).
* Inventing or adjusting a confidence value (§33).
* Launching a browser, re-crawling, re-running OmniParser or OCR, re-reading
  the DOM, or touching the network (§49).
* Calling an LLM (§3).
* Copying raw DOM, screenshots, network bodies or credentials (§50).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from agentqe.knowledge.index import KnowledgeIndex
from agentqe.knowledge.interfaces import ApplicationKnowledgeBuilder, KnowledgeBuildError
from agentqe.knowledge.knowledge_model import build_summaries
from agentqe.knowledge.schemas import (
    ASSOCIATED_WITH,
    BELONGS_TO,
    CALLS,
    CONTAINS,
    DEFAULT_BUILDER_NAME,
    DERIVATION_STRUCTURAL,
    DERIVATION_TRANSLATED,
    ENTITY_API_ENDPOINT,
    ENTITY_APPLICATION,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REPOSITORY_SYMBOL,
    ENTITY_REQUIREMENT,
    ENTITY_TECHNOLOGY,
    ENTITY_USER_FLOW,
    HAS_CONTROL,
    HAS_FIELD,
    HAS_FORM,
    IMPLEMENTED_BY,
    INFERRED,
    KNOWLEDGE_MODEL_VERSION,
    LIKELY_TRIGGERS,
    NAVIGATES_TO,
    OBSERVED,
    OBSERVED_ON,
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
    slugify,
    weakest_status,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeLimits:
    """
    Safety rails so a pathological unified model cannot exhaust memory.

    Phase 1.5F already caps itself (3000 controls, 8000 relationships), so these
    ceilings are deliberately generous — they exist to fail loudly with a
    recorded warning rather than to shape normal output.
    """
    max_entities: int = 60000
    max_relationships: int = 200000
    max_evidence_refs_per_entity: int = 24
    max_flow_steps: int = 200

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_entities": self.max_entities,
            "max_relationships": self.max_relationships,
            "max_evidence_refs_per_entity": self.max_evidence_refs_per_entity,
            "max_flow_steps": self.max_flow_steps,
        }


#: Values in a technology stack that carry no information and must not become
#: technology entities (§19).
_EMPTY_TECHNOLOGY_VALUES = {"", "unknown", "none", "n/a", "na", "undefined", "null", "-"}


# ---------------------------------------------------------------------------
# Build state
# ---------------------------------------------------------------------------

@dataclass
class _BuildState:
    """Mutable bookkeeping for a single build. Never reused across builds."""
    entities: List[KnowledgeEntity] = field(default_factory=list)
    entities_by_id: Dict[str, KnowledgeEntity] = field(default_factory=dict)
    relationships: List[KnowledgeRelationship] = field(default_factory=list)
    relationships_by_key: Dict[Tuple[str, str, str], KnowledgeRelationship] = field(default_factory=dict)

    #: Phase 1.5F entity id -> knowledge entity id.
    uid_to_kid: Dict[str, str] = field(default_factory=dict)
    #: Phase 1.5F entity id -> its Phase 1.5F entity type.
    uid_to_type: Dict[str, str] = field(default_factory=dict)
    #: Phase 1.5F entity id -> the raw Phase 1.5F dict.
    uid_to_source: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    #: (source_uid, target_uid) -> list of Phase 1.5F relationship dicts, used to
    #: inherit an honest status for structural edges (§32) instead of assuming.
    unified_edges: Dict[Tuple[str, str], List[Dict[str, Any]]] = field(default_factory=dict)

    warnings: List[str] = field(default_factory=list)
    application_entity_id: Optional[str] = None

    def warn(self, message: str) -> None:
        if message not in self.warnings and len(self.warnings) < 200:
            self.warnings.append(message)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class DeterministicApplicationKnowledgeBuilder(ApplicationKnowledgeBuilder):
    """
    The Phase 1.5G reference builder.

    Deterministic: for the same ``UnifiedApplicationModel`` it produces the same
    entity ids, relationship ids, counts, indexes and serialized output, with the
    sole exception of ``provenance.generated_at`` / ``provenance.duration_ms``
    (see ``VOLATILE_PROVENANCE_FIELDS`` and
    ``serialization.deterministic_fingerprint``).
    """

    def __init__(
        self,
        limits: Optional[KnowledgeLimits] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.limits = limits or KnowledgeLimits()
        #: Injectable so tests can pin the timestamp and compare full output.
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- public API ---------------------------------------------------------

    def get_builder_info(self) -> Dict[str, Any]:
        return {
            "builder": DEFAULT_BUILDER_NAME,
            "knowledge_model_version": KNOWLEDGE_MODEL_VERSION,
            "llm_used": False,
            "deterministic": True,
            "limits": self.limits.to_dict(),
        }

    def build(self, unified_model: Any) -> ApplicationKnowledgeModel:
        started = time.time()
        data = self._as_dict(unified_model)
        state = _BuildState()

        try:
            self._index_source_entities(state, data)
            self._allocate_entity_ids(state, data)

            # Entities, in a fixed order so `entities` is stable and readable.
            self._build_application_entity(state, data)
            self._build_technology_entities(state, data)
            self._build_module_entities(state, data)
            self._build_page_entities(state, data)
            self._build_form_entities(state, data)
            self._build_control_entities(state, data)
            self._build_api_entities(state, data)
            self._build_flow_entities(state, data)
            self._build_requirement_entities(state, data)
            self._build_repository_entities(state, data)

            # Relationships: translate Phase 1.5F first so that the structural
            # pass finds an existing, honestly-statused edge to merge into.
            self._translate_unified_relationships(state, data)
            self._build_structural_relationships(state, data)
        except KnowledgeBuildError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise KnowledgeBuildError(
                f"Knowledge model construction failed: {exc}"
            ) from exc

        model = ApplicationKnowledgeModel(
            model_version=KNOWLEDGE_MODEL_VERSION,
            entities=state.entities,
            relationships=state.relationships,
        )
        if state.application_entity_id:
            app_entity = state.entities_by_id.get(state.application_entity_id)
            if app_entity is not None:
                model.application = app_entity.to_dict()

        index = KnowledgeIndex.build(model)
        model.indexes = index.to_dict()
        model.summaries = build_summaries(model, index)

        fusion_metadata = data.get("fusion_metadata") or {}
        model.provenance = KnowledgeProvenance(
            fusion_version=fusion_metadata.get("fusion_version"),
            fusion_timestamp=fusion_metadata.get("fusion_timestamp"),
            fusion_engine=fusion_metadata.get("engine"),
            generated_at=self._clock().isoformat(),
            builder=DEFAULT_BUILDER_NAME,
            llm_used=False,
            duration_ms=round((time.time() - started) * 1000.0, 3),
            evidence_sources=list(fusion_metadata.get("sources") or []),
            warnings=list(state.warnings),
        )
        model.metadata = {
            "limits": self.limits.to_dict(),
            "entity_types_emitted": sorted({e.entity_type for e in model.entities}),
            "relationship_types_emitted": sorted({r.relationship for r in model.relationships}),
            "source_entity_count": len(state.uid_to_kid),
            "source_relationship_count": len(data.get("relationships") or []),
            "translated_relationship_count": sum(
                1 for r in model.relationships if r.derivation_kind == DERIVATION_TRANSLATED
            ),
            "structural_relationship_count": sum(
                1 for r in model.relationships if r.derivation_kind == DERIVATION_STRUCTURAL
            ),
        }
        return model

    # -- input normalization ------------------------------------------------

    @staticmethod
    def _as_dict(unified_model: Any) -> Dict[str, Any]:
        """Accept a ``UnifiedApplicationModel``, its dict form, or nothing."""
        if unified_model is None:
            return {}
        if hasattr(unified_model, "to_dict"):
            data = unified_model.to_dict()
        else:
            data = unified_model
        if not isinstance(data, dict):
            raise KnowledgeBuildError(
                f"unified_model must be a UnifiedApplicationModel or mapping, got "
                f"{type(unified_model).__name__}.",
                error_code="KNOWLEDGE_INPUT_TYPE",
            )
        return data

    @staticmethod
    def _collection(data: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
        items = data.get(key) or []
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict)]

    # -- pass 1: index the source model ------------------------------------

    _SOURCE_COLLECTIONS: Tuple[Tuple[str, str], ...] = (
        ("pages", ENTITY_PAGE),
        ("controls", ENTITY_CONTROL),
        ("forms", ENTITY_FORM),
        ("api_endpoints", ENTITY_API_ENDPOINT),
        ("user_flows", ENTITY_USER_FLOW),
        ("modules", ENTITY_MODULE),
        ("requirements", ENTITY_REQUIREMENT),
    )

    def _index_source_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for key, entity_type in self._SOURCE_COLLECTIONS:
            for item in self._collection(data, key):
                uid = item.get("id")
                if not uid or not isinstance(uid, str):
                    state.warn(f"Skipped a {entity_type} in the unified model because it has no id.")
                    continue
                if uid in state.uid_to_source:
                    state.warn(
                        f"Unified model contains duplicate id '{uid}'; the knowledge model keeps "
                        "the first occurrence."
                    )
                    continue
                state.uid_to_source[uid] = item
                state.uid_to_type[uid] = entity_type

        for rel in self._collection(data, "relationships"):
            key = (rel.get("source_id") or "", rel.get("target_id") or "")
            state.unified_edges.setdefault(key, []).append(rel)

    # -- pass 2: deterministic id allocation (§8) ---------------------------

    def _allocate_entity_ids(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """
        Allocate every knowledge id up front, so relationship translation can
        resolve both endpoints without depending on entity creation order.
        """
        candidates: List[IdCandidate] = []
        # Page slugs are needed to qualify control/form ids, so pages go first
        # and are resolved in their own allocation round.
        page_candidates = [self._page_id_candidate(item) for item in self._collection(data, "pages")]
        page_ids = allocate_ids(page_candidates)
        for item in self._collection(data, "pages"):
            uid = item.get("id")
            key = self._page_key(item)
            if uid and key in page_ids:
                state.uid_to_kid[uid] = page_ids[key]

        def page_base(source_page_id: Any) -> str:
            """Bare slug of a page's knowledge id, used to qualify children."""
            kid = state.uid_to_kid.get(str(source_page_id or ""))
            if not kid:
                return ""
            return kid.split(":", 1)[1] if ":" in kid else kid

        for item in self._collection(data, "modules"):
            candidates.append(self._module_id_candidate(item))
        for item in self._collection(data, "forms"):
            candidates.append(self._form_id_candidate(item, page_base(item.get("page_id"))))
        for item in self._collection(data, "controls"):
            candidates.append(self._control_id_candidate(item, page_base(item.get("page_id"))))
        for item in self._collection(data, "api_endpoints"):
            candidates.append(self._api_id_candidate(item))
        for item in self._collection(data, "user_flows"):
            candidates.append(self._flow_id_candidate(item))
        for item in self._collection(data, "requirements"):
            candidates.append(self._requirement_id_candidate(item))

        allocated = allocate_ids(candidates)
        for key, entity_type in self._SOURCE_COLLECTIONS:
            if key == "pages":
                continue
            for item in self._collection(data, key):
                uid = item.get("id")
                identity = self._identity_key(entity_type, item)
                if uid and identity in allocated:
                    state.uid_to_kid[uid] = allocated[identity]

        if len(state.uid_to_kid) > self.limits.max_entities:
            state.warn(
                f"Unified model holds {len(state.uid_to_kid)} entities, above the "
                f"max_entities limit of {self.limits.max_entities}; the knowledge model "
                "was built anyway but may be unusually large."
            )

    # -- identity keys ------------------------------------------------------

    @staticmethod
    def _identity_key(entity_type: str, item: Dict[str, Any]) -> str:
        """
        A stable, unique identity string per source entity.

        Includes the Phase 1.5F id (already unique) plus the evidence references
        that distinguish the entity, so the hash-based collision fallback is
        content-derived rather than position-derived.
        """
        uid = str(item.get("id") or "")
        if entity_type == ENTITY_PAGE:
            return f"page|{uid}|{item.get('normalized_url') or item.get('url') or ''}"
        if entity_type == ENTITY_CONTROL:
            return (
                f"control|{uid}|{item.get('page_id') or ''}|{item.get('dom_ref') or ''}"
                f"|{item.get('visual_ref') or ''}|{item.get('accessibility_ref') or ''}"
            )
        if entity_type == ENTITY_FORM:
            return f"form|{uid}|{item.get('page_id') or ''}|{item.get('dom_ref') or ''}"
        if entity_type == ENTITY_API_ENDPOINT:
            return (
                f"api|{uid}|{str(item.get('method') or '').upper()}"
                f"|{item.get('host') or ''}|{item.get('path') or ''}"
            )
        if entity_type == ENTITY_USER_FLOW:
            return f"flow|{uid}|{item.get('name') or ''}|{item.get('source') or ''}"
        if entity_type == ENTITY_MODULE:
            return f"module|{uid}|{item.get('name') or ''}|{item.get('source') or ''}"
        if entity_type == ENTITY_REQUIREMENT:
            return f"requirement|{uid}"
        return f"{entity_type}|{uid}"

    def _page_key(self, item: Dict[str, Any]) -> str:
        return self._identity_key(ENTITY_PAGE, item)

    # -- id candidates per type --------------------------------------------

    @staticmethod
    def _url_slug_parts(url: Any) -> Tuple[str, str]:
        """Return ``(path_slug, host_slug)`` for a URL. ``/`` becomes ``root``."""
        try:
            parts = urlsplit(str(url or ""))
        except Exception:
            return "", ""
        path_slug = slugify(parts.path, fallback="") or "root"
        host_slug = slugify(parts.netloc, fallback="")
        return path_slug, host_slug

    def _page_id_candidate(self, item: Dict[str, Any]) -> IdCandidate:
        path_slug, host_slug = self._url_slug_parts(item.get("url") or item.get("normalized_url"))
        base = (
            path_slug
            or slugify(item.get("title"))
            or slugify(item.get("page_type"))
            or slugify(item.get("id"), fallback="page")
        )
        tiers = [f"page:{base}"]
        if host_slug:
            tiers.append(f"page:{base}_{host_slug}")
        return IdCandidate(key=self._page_key(item), tiers=tuple(tiers))

    def _module_id_candidate(self, item: Dict[str, Any]) -> IdCandidate:
        base = slugify(item.get("name")) or slugify(item.get("id"), fallback="module")
        tiers = [f"module:{base}"]
        source_slug = slugify(item.get("source"))
        if source_slug:
            tiers.append(f"module:{base}_{source_slug}")
        return IdCandidate(key=self._identity_key(ENTITY_MODULE, item), tiers=tuple(tiers))

    def _form_id_candidate(self, item: Dict[str, Any], page_base: str) -> IdCandidate:
        action_slug = ""
        if item.get("action"):
            action_slug, _ = self._url_slug_parts(item.get("action"))
            if action_slug == "root":
                action_slug = ""
        base = (
            slugify(item.get("name"))
            or slugify(item.get("semantic_role"))
            or action_slug
            or "form"
        )
        tiers = [f"form:{base}"]
        if page_base:
            tiers.append(f"form:{page_base}_{base}")
        return IdCandidate(key=self._identity_key(ENTITY_FORM, item), tiers=tuple(tiers))

    def _control_id_candidate(self, item: Dict[str, Any], page_base: str) -> IdCandidate:
        base = (
            slugify(item.get("label"), max_length=40)
            or slugify(item.get("text"), max_length=40)
            or slugify(item.get("dom_name"), max_length=40)
            or slugify(item.get("dom_id"), max_length=40)
            or slugify(item.get("semantic_role"), max_length=40)
            or slugify(item.get("role"), max_length=40)
            or slugify(item.get("dom_tag"), max_length=40)
            or slugify(item.get("type"), max_length=40)
            or "control"
        )
        tiers = [f"control:{base}"]
        if page_base:
            tiers.append(f"control:{page_base}_{base}")
        return IdCandidate(key=self._identity_key(ENTITY_CONTROL, item), tiers=tuple(tiers))

    def _api_id_candidate(self, item: Dict[str, Any]) -> IdCandidate:
        method = str(item.get("method") or "get").strip().lower() or "get"
        path = str(item.get("path") or "").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        host = str(item.get("host") or "").strip()
        tiers = [f"api:{method}:{path}"]
        if host:
            tiers.append(f"api:{method}:{host}{path}")
        return IdCandidate(key=self._identity_key(ENTITY_API_ENDPOINT, item), tiers=tuple(tiers))

    def _flow_id_candidate(self, item: Dict[str, Any]) -> IdCandidate:
        role_slug = slugify(item.get("semantic_role"))
        name_slug = slugify(item.get("name"))
        base = role_slug or name_slug or slugify(item.get("id"), fallback="flow")
        tiers = [f"flow:{base}"]
        if name_slug and name_slug != base:
            tiers.append(f"flow:{name_slug}")
        source_slug = slugify(item.get("source"))
        if source_slug:
            tiers.append(f"flow:{base}_{source_slug}")
        return IdCandidate(key=self._identity_key(ENTITY_USER_FLOW, item), tiers=tuple(tiers))

    @staticmethod
    def _requirement_id_candidate(item: Dict[str, Any]) -> IdCandidate:
        uid = str(item.get("id") or "").strip()
        # Requirement ids are already stable and human-meaningful (REQ-001),
        # so they are preserved verbatim rather than slugified (§8).
        base = uid or "requirement"
        return IdCandidate(
            key=f"requirement|{uid}",
            tiers=(f"requirement:{base}",),
        )

    # -- entity construction -----------------------------------------------

    def _add_entity(self, state: _BuildState, entity: KnowledgeEntity) -> Optional[KnowledgeEntity]:
        if entity.id in state.entities_by_id:
            state.warn(
                f"Duplicate knowledge entity id '{entity.id}' was suppressed; id allocation "
                "should have prevented this."
            )
            return state.entities_by_id[entity.id]
        if len(state.entities) >= self.limits.max_entities:
            state.warn(
                f"max_entities limit ({self.limits.max_entities}) reached; further entities "
                "were not added."
            )
            return None
        state.entities.append(entity)
        state.entities_by_id[entity.id] = entity
        return entity

    def _refs(self, refs: Any) -> List[str]:
        """Copy evidence refs verbatim, de-duplicated and capped."""
        out: List[str] = []
        for ref in (refs or []):
            if isinstance(ref, str) and ref and ref not in out:
                out.append(ref)
            if len(out) >= self.limits.max_evidence_refs_per_entity:
                break
        return out

    # -- application (§10) --------------------------------------------------

    def _build_application_entity(self, state: _BuildState, data: Dict[str, Any]) -> None:
        app = data.get("application") or {}
        if not isinstance(app, dict):
            app = {}
        pages = self._collection(data, "pages")

        display_name = (
            str(app.get("name") or "").strip()
            or str(app.get("module_name") or "").strip()
            or str(app.get("url") or "").strip()
            or "Application"
        )
        entity_id = "application:app"
        status = app.get("observation_status") or (OBSERVED if pages else UNKNOWN)
        if status not in (OBSERVED, INFERRED, UNKNOWN):
            status = UNKNOWN

        evidence_refs = self._refs(app.get("evidence_refs"))
        if not evidence_refs:
            # Keep the application node traceable even when fusion recorded no
            # refs (e.g. a repository-only or requirement-only run).
            evidence_refs = ["context:application:0"]

        entity = KnowledgeEntity(
            id=entity_id,
            entity_type=ENTITY_APPLICATION,
            name=display_name,
            display_name=display_name,
            canonical_name=slugify(display_name, fallback="application"),
            description=self._describe_application(app, len(pages)),
            properties={
                "url": app.get("url"),
                "app_type": app.get("app_type"),
                "framework": app.get("framework"),
                "module_name": app.get("module_name"),
                "repo_url": app.get("repo_url"),
                "technology_stack": app.get("technology_stack") or {},
                "page_count": len(pages),
            },
            source_entity_id=None,
            source_entity_type="application",
            evidence_refs=evidence_refs,
            status=status,
            inference_reason=(
                "No page was successfully analysed, so the application itself could not be "
                "characterised from observation."
                if status == UNKNOWN
                else None
            ),
        )
        self._add_entity(state, entity)
        state.application_entity_id = entity_id

    @staticmethod
    def _describe_application(app: Dict[str, Any], page_count: int) -> str:
        app_type = app.get("app_type") or "application"
        url = app.get("url")
        parts = [f"{app_type.capitalize()} application"]
        if url:
            parts.append(f"at {url}")
        parts.append(f"with {page_count} analysed page(s)")
        return " ".join(parts) + "."

    # -- technology (§19) ---------------------------------------------------

    def _build_technology_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """
        Technology entities come only from what upstream analysis already
        reported (``application.technology_stack`` / ``application.framework``),
        which is the sole technology evidence Phase 1.5F carries.

        They are always ``inferred``: the knowledge builder can see *that* a
        stack entry was reported, but not *how* it was detected — repository
        manifest parsing and page-text sniffing both land in the same field. It
        would be dishonest to call that ``observed`` (§19, §32).
        """
        app = data.get("application") or {}
        if not isinstance(app, dict):
            return
        stack = app.get("technology_stack") or {}
        if not isinstance(stack, dict):
            stack = {}

        # canonical slug -> {"display": str, "categories": [...], "refs": [...]}
        collected: Dict[str, Dict[str, Any]] = {}

        def collect(value: Any, category: str, ref: str) -> None:
            if not isinstance(value, str):
                return
            cleaned = value.strip()
            if cleaned.lower() in _EMPTY_TECHNOLOGY_VALUES:
                return
            slug = slugify(cleaned)
            if not slug:
                return
            bucket = collected.setdefault(
                slug, {"display": cleaned, "categories": [], "refs": []}
            )
            if category not in bucket["categories"]:
                bucket["categories"].append(category)
            if ref not in bucket["refs"]:
                bucket["refs"].append(ref)

        for key in sorted(stack.keys(), key=str):
            value = stack[key]
            ref = f"context:technology_stack:{slugify(key, fallback='entry')}"
            if isinstance(value, str):
                collect(value, str(key), ref)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item, str(key), ref)

        collect(app.get("framework"), "framework", "context:framework:0")

        for slug in sorted(collected):
            info = collected[slug]
            categories = info["categories"]
            entity = KnowledgeEntity(
                id=f"technology:{slug}",
                entity_type=ENTITY_TECHNOLOGY,
                name=info["display"],
                display_name=info["display"],
                canonical_name=slug,
                description=(
                    f"{info['display']} reported as the application's "
                    f"{', '.join(categories)} technology."
                ),
                properties={
                    "value": info["display"],
                    "categories": list(categories),
                    "source_fields": list(info["refs"]),
                },
                source_entity_id=None,
                source_entity_type="application.technology_stack",
                evidence_refs=list(info["refs"]),
                evidence_sources=["repository"] if "framework" in categories else [],
                status=INFERRED,
                inference_reason=(
                    "Reported by upstream technology-stack analysis "
                    f"({', '.join(info['refs'])}). The knowledge builder cannot verify how the "
                    "technology was detected, so the entry is recorded as inferred rather than "
                    "observed."
                ),
            )
            self._add_entity(state, entity)

    # -- modules (§11) ------------------------------------------------------

    def _build_module_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "modules"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            display = str(item.get("name") or "").strip() or (uid or "module")
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_MODULE,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="module"),
                description=(
                    f"Module '{display}' identified by {item.get('source') or 'evidence fusion'}, "
                    f"spanning {len(item.get('pages') or [])} page(s)."
                ),
                properties={
                    "source": item.get("source"),
                    "page_ids": self._map_ids(state, item.get("pages")),
                    "control_ids": self._map_ids(state, item.get("controls")),
                    "form_ids": self._map_ids(state, item.get("forms")),
                    "api_endpoint_ids": self._map_ids(state, item.get("api_endpoints")),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_MODULE,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                repository_refs=[dict(r) for r in (item.get("repository_refs") or [])],
                status=self._status(item),
                inference_reason=item.get("inference_reason"),
            )
            self._add_entity(state, entity)

    # -- pages (§12) --------------------------------------------------------

    def _build_page_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "pages"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            display = (
                str(item.get("title") or "").strip()
                or str(item.get("url") or "").strip()
                or (uid or "page")
            )
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_PAGE,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="page"),
                description=self._describe_page(item),
                properties={
                    "url": item.get("url"),
                    "normalized_url": item.get("normalized_url"),
                    "title": item.get("title"),
                    "page_type": item.get("page_type"),
                    "page_type_status": item.get("page_type_status"),
                    "depth": item.get("depth"),
                    "crawl_status": item.get("crawl_status"),
                    "page_index": item.get("page_index"),
                    "crawl_ref": item.get("crawl_ref"),
                    "screenshot_ref": item.get("screenshot_ref"),
                    "visual_ui_status": item.get("visual_ui_status"),
                    "control_ids": self._map_ids(state, item.get("controls")),
                    "form_ids": self._map_ids(state, item.get("forms")),
                    "api_endpoint_ids": self._map_ids(state, item.get("api_endpoints")),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_PAGE,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                repository_refs=[dict(r) for r in (item.get("repository_refs") or [])],
                status=self._status(item),
            )
            self._add_entity(state, entity)

    @staticmethod
    def _describe_page(item: Dict[str, Any]) -> str:
        page_type = item.get("page_type") or "page"
        title = item.get("title") or item.get("url") or "untitled"
        counts = (
            f"{len(item.get('controls') or [])} control(s), "
            f"{len(item.get('forms') or [])} form(s), "
            f"{len(item.get('api_endpoints') or [])} observed endpoint(s)"
        )
        return f"{str(page_type).replace('_', ' ').capitalize()} '{title}' with {counts}."

    # -- forms (§14) --------------------------------------------------------

    def _build_form_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "forms"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            display = (
                str(item.get("name") or "").strip()
                or (str(item.get("semantic_role") or "").replace("_", " ").title().strip())
                or (uid or "form")
            )
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_FORM,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="form"),
                description=(
                    f"Form '{display}' with {len(item.get('fields') or [])} field(s)"
                    + (
                        f", associated with {len(item.get('observed_api_endpoints') or [])} "
                        "observed endpoint(s)."
                        if item.get("observed_api_endpoints")
                        else "."
                    )
                ),
                properties={
                    "name": item.get("name"),
                    "action": item.get("action"),
                    "method": item.get("method"),
                    "semantic_role": item.get("semantic_role"),
                    "semantic_role_status": item.get("semantic_role_status"),
                    "page_id": state.uid_to_kid.get(str(item.get("page_id") or "")),
                    "source_page_id": item.get("page_id"),
                    "field_ids": self._map_ids(state, item.get("fields")),
                    "submit_control_id": state.uid_to_kid.get(
                        str(item.get("submit_control") or "")
                    ),
                    "api_endpoint_ids": self._map_ids(state, item.get("observed_api_endpoints")),
                    "dom_ref": item.get("dom_ref"),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_FORM,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                repository_refs=[dict(r) for r in (item.get("repository_refs") or [])],
                status=self._status(item),
                confidence=item.get("confidence"),
                confidence_basis=item.get("confidence_basis"),
                inference_reason=item.get("inference_reason"),
            )
            self._add_entity(state, entity)

    # -- controls (§13) -----------------------------------------------------

    def _build_control_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "controls"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            display = (
                str(item.get("label") or "").strip()
                or str(item.get("text") or "").strip()
                or str(item.get("dom_name") or "").strip()
                or str(item.get("dom_id") or "").strip()
                or f"{item.get('type') or 'control'}"
            )
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_CONTROL,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="control"),
                description=self._describe_control(item),
                properties={
                    # Phase 1.5F facts, preserved without loss (§13).
                    "type": item.get("type"),
                    "label": item.get("label"),
                    "text": item.get("text"),
                    "semantic_role": item.get("semantic_role"),
                    "semantic_role_status": item.get("semantic_role_status"),
                    "interactable": item.get("interactable"),
                    "observation_status": item.get("observation_status"),
                    "page_id": state.uid_to_kid.get(str(item.get("page_id") or "")),
                    "source_page_id": item.get("page_id"),
                    "form_id": state.uid_to_kid.get(str(item.get("form_id") or "")),
                    "source_form_id": item.get("form_id"),
                    "dom_ref": item.get("dom_ref"),
                    "accessibility_ref": item.get("accessibility_ref"),
                    "visual_ref": item.get("visual_ref"),
                    "bbox_pixels": item.get("bbox_pixels"),
                    "bbox_normalized": item.get("bbox_normalized"),
                    "dom_id": item.get("dom_id"),
                    "dom_tag": item.get("dom_tag"),
                    "dom_name": item.get("dom_name"),
                    "dom_type": item.get("dom_type"),
                    "role": item.get("role"),
                    "href": item.get("href"),
                    "correlation": item.get("correlation") or {},
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_CONTROL,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                repository_refs=[dict(r) for r in (item.get("repository_refs") or [])],
                status=self._status(item),
                confidence=item.get("confidence"),
                confidence_basis=item.get("confidence_basis"),
                inference_reason=item.get("inference_reason"),
            )
            self._add_entity(state, entity)

    @staticmethod
    def _describe_control(item: Dict[str, Any]) -> str:
        ctype = item.get("type") or "control"
        label = item.get("label") or item.get("text")
        role = item.get("semantic_role")
        parts = [str(ctype).capitalize()]
        if label:
            parts.append(f"labelled '{label}'")
        if role:
            parts.append(f"interpreted as {str(role).replace('_', ' ')}")
        return " ".join(parts) + "."

    # -- api endpoints (§15) ------------------------------------------------

    def _build_api_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """
        API entities carry only the non-sensitive shape metadata Phase 1.5F
        already normalized. No headers, cookies, tokens, credentials or bodies
        are copied (§15, §50) — the unified model does not contain them, and
        nothing here reintroduces them.
        """
        for item in self._collection(data, "api_endpoints"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            method = str(item.get("method") or "GET").upper()
            path = item.get("path") or "/"
            display = f"{method} {path}"
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_API_ENDPOINT,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="api"),
                description=(
                    f"{method} {path} observed {item.get('observation_count') or 0} time(s) on "
                    f"{len(item.get('observed_on_pages') or [])} page(s)."
                ),
                properties={
                    "method": method,
                    "path": path,
                    "host": item.get("host"),
                    "url": item.get("url"),
                    "observed_on_page_ids": self._map_ids(state, item.get("observed_on_pages")),
                    "source_observed_on_pages": list(item.get("observed_on_pages") or []),
                    "request_metadata": item.get("request_metadata") or {},
                    "response_metadata": item.get("response_metadata") or {},
                    "observation_count": item.get("observation_count"),
                    "failure_count": item.get("failure_count"),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_API_ENDPOINT,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                repository_refs=[dict(r) for r in (item.get("repository_refs") or [])],
                status=self._status(item),
            )
            self._add_entity(state, entity)

    # -- user flows (§16, §31) ---------------------------------------------

    def _build_flow_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "user_flows"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            display = str(item.get("name") or "").strip() or (uid or "flow")
            steps = self._build_flow_steps(state, item)
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_USER_FLOW,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="flow"),
                description=(
                    f"User flow '{display}' ({item.get('source') or 'unknown source'}) with "
                    f"{len(steps)} step(s)."
                ),
                properties={
                    "source": item.get("source"),
                    "semantic_role": item.get("semantic_role"),
                    "steps": steps,
                    "page_ids": self._map_ids(state, item.get("page_ids")),
                    "control_ids": self._map_ids(state, item.get("control_ids")),
                    "api_endpoint_ids": self._map_ids(state, item.get("api_endpoint_ids")),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_USER_FLOW,
                evidence_refs=self._refs(item.get("evidence_refs")),
                evidence_sources=list(item.get("evidence_sources") or []),
                requirement_refs=self._map_requirement_refs(state, item.get("requirement_refs")),
                status=self._status(item),
                confidence=item.get("confidence"),
                confidence_basis=item.get("confidence_basis"),
                inference_reason=item.get("inference_reason"),
            )
            self._add_entity(state, entity)

    def _build_flow_steps(self, state: _BuildState, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Translate ``UserFlowStep`` into knowledge-id steps (§31).

        Only steps that Phase 1.5F actually produced are represented; no step is
        fabricated, and each step keeps its own ``observation_status`` so a
        consumer can tell a real navigation from an un-executed click.
        """
        steps: List[Dict[str, Any]] = []
        raw_steps = item.get("steps") or []
        if not isinstance(raw_steps, list):
            return steps
        for raw in raw_steps[: self.limits.max_flow_steps]:
            if not isinstance(raw, dict):
                continue
            action = raw.get("action")
            control_kid = state.uid_to_kid.get(str(raw.get("control_id") or ""))
            api_kid = state.uid_to_kid.get(str(raw.get("api_endpoint_id") or ""))
            page_kid = state.uid_to_kid.get(str(raw.get("page_id") or ""))

            # The step's primary entity is the thing the action acts upon.
            if action in ("input", "click") and control_kid:
                entity_id, entity_type = control_kid, ENTITY_CONTROL
            elif action == "api_call" and api_kid:
                entity_id, entity_type = api_kid, ENTITY_API_ENDPOINT
            elif page_kid:
                entity_id, entity_type = page_kid, ENTITY_PAGE
            else:
                entity_id, entity_type = None, None

            steps.append({
                "order": raw.get("order"),
                "action": action,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "page_id": page_kid,
                "control_id": control_kid,
                "api_endpoint_id": api_kid,
                "description": raw.get("description") or "",
                "observation_status": raw.get("observation_status") or UNKNOWN,
                "inference_reason": raw.get("inference_reason"),
                "evidence_refs": self._refs(raw.get("evidence_refs")),
            })
        return steps

    # -- requirements (§17) -------------------------------------------------

    def _build_requirement_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for item in self._collection(data, "requirements"):
            uid = item.get("id")
            kid = state.uid_to_kid.get(uid or "")
            if not kid:
                continue
            description = str(item.get("description") or "").strip()
            display = uid or "requirement"
            entity = KnowledgeEntity(
                id=kid,
                entity_type=ENTITY_REQUIREMENT,
                name=display,
                display_name=display,
                canonical_name=slugify(display, fallback="requirement"),
                description=description or None,
                properties={
                    "requirement_id": uid,
                    "text": description,
                    "source": item.get("source"),
                    "keywords": list(item.get("keywords") or []),
                },
                source_entity_id=uid,
                source_entity_type=ENTITY_REQUIREMENT,
                evidence_refs=self._refs(item.get("evidence_refs")),
                status=self._status(item),
            )
            self._add_entity(state, entity)

    # -- repository (§18) ---------------------------------------------------

    def _build_repository_entities(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """
        Repository entities are collected from the ``repository_refs`` that
        Phase 1.5F attached to pages, modules and controls.

        No source-code mapping is invented: a file becomes an entity only
        because fusion already recorded a (filename-based, ``inferred``) match,
        and the original ``match_reason`` is carried onto the edge.
        """
        # path -> {"symbols": {...}, "refs": [...], "reasons": [...]}
        files: Dict[str, Dict[str, Any]] = {}

        for uid, source in state.uid_to_source.items():
            for ref in (source.get("repository_refs") or []):
                if not isinstance(ref, dict):
                    continue
                path = normalize_path(ref.get("file"))
                if not path:
                    continue
                bucket = files.setdefault(
                    path,
                    {"symbols": {}, "evidence_refs": [], "reasons": [], "linked": []},
                )
                symbol = str(ref.get("symbol") or "").strip()
                if symbol:
                    bucket["symbols"][symbol] = ref.get("symbol_status") or INFERRED
                evidence_ref = ref.get("evidence_ref")
                if isinstance(evidence_ref, str) and evidence_ref not in bucket["evidence_refs"]:
                    bucket["evidence_refs"].append(evidence_ref)
                reason = ref.get("match_reason")
                if isinstance(reason, str) and reason not in bucket["reasons"]:
                    bucket["reasons"].append(reason)
                kid = state.uid_to_kid.get(uid)
                if kid and kid not in bucket["linked"]:
                    bucket["linked"].append(kid)

        for path in sorted(files):
            info = files[path]
            file_id = f"repo:file:{path}"
            display = path.rsplit("/", 1)[-1] or path
            evidence_refs = info["evidence_refs"] or [f"repository:{path}"]
            self._add_entity(state, KnowledgeEntity(
                id=file_id,
                entity_type=ENTITY_REPOSITORY_FILE,
                name=display,
                display_name=path,
                canonical_name=slugify(path, fallback="file"),
                description=f"Repository file {path}.",
                properties={
                    "path": path,
                    "file_name": display,
                    "symbols": sorted(info["symbols"].keys()),
                    "match_reasons": list(info["reasons"]),
                    "linked_entity_ids": list(info["linked"]),
                },
                source_entity_id=None,
                source_entity_type="repository_refs",
                evidence_refs=list(evidence_refs),
                evidence_sources=["repository"],
                status=INFERRED,
                inference_reason=(
                    "File associated by Phase 1.5F repository analysis on a filename match ("
                    + "; ".join(info["reasons"] or ["unspecified match"])
                    + "). The file itself was not parsed."
                ),
            ))

            for symbol in sorted(info["symbols"]):
                symbol_status = info["symbols"][symbol]
                self._add_entity(state, KnowledgeEntity(
                    id=f"repo:symbol:{path}:{symbol}",
                    entity_type=ENTITY_REPOSITORY_SYMBOL,
                    name=symbol,
                    display_name=symbol,
                    canonical_name=slugify(symbol, fallback="symbol"),
                    description=f"Symbol '{symbol}' attributed to {path}.",
                    properties={
                        "symbol": symbol,
                        "file_path": path,
                        "symbol_status": symbol_status,
                    },
                    source_entity_id=None,
                    source_entity_type="repository_refs",
                    evidence_refs=list(evidence_refs),
                    evidence_sources=["repository"],
                    status=symbol_status if symbol_status in (OBSERVED, INFERRED, UNKNOWN) else INFERRED,
                    inference_reason=(
                        "Symbol name derived from the file name by Phase 1.5F repository "
                        "analysis; the file was not parsed, so the symbol is not confirmed to "
                        "exist in the source."
                    ),
                ))

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _status(item: Dict[str, Any]) -> str:
        """Copy Phase 1.5F ``observation_status`` verbatim (§32)."""
        status = item.get("observation_status")
        return status if status in (OBSERVED, INFERRED, UNKNOWN) else UNKNOWN

    @staticmethod
    def _map_ids(state: _BuildState, source_ids: Any) -> List[str]:
        """Map a list of Phase 1.5F ids to knowledge ids, dropping unresolved."""
        out: List[str] = []
        for source_id in (source_ids or []):
            kid = state.uid_to_kid.get(str(source_id))
            if kid and kid not in out:
                out.append(kid)
        return out

    @staticmethod
    def _map_requirement_refs(state: _BuildState, refs: Any) -> List[str]:
        out: List[str] = []
        for ref in (refs or []):
            kid = state.uid_to_kid.get(str(ref))
            value = kid or f"requirement:{ref}"
            if value not in out:
                out.append(value)
        return out

    # -- relationship emission ---------------------------------------------

    def _add_relationship(
        self,
        state: _BuildState,
        source_id: Optional[str],
        relationship: str,
        target_id: Optional[str],
        status: str,
        *,
        confidence: Optional[float] = None,
        confidence_basis: Optional[str] = None,
        inference_reason: Optional[str] = None,
        evidence_refs: Optional[Iterable[str]] = None,
        source_relationship_id: Optional[str] = None,
        derivation_kind: str = DERIVATION_STRUCTURAL,
        derivation: Optional[str] = None,
    ) -> Optional[KnowledgeRelationship]:
        """
        Emit one edge, merging into an existing edge with the same
        (source, relationship, target) triple.

        Merge policy: the first edge wins for status/confidence/reason (the
        translated pass runs first, so a Phase 1.5F-backed status is never
        overwritten by a structurally-derived guess); evidence references and
        derivation notes are unioned so no provenance is lost.
        """
        if not source_id or not target_id:
            return None
        if source_id not in state.entities_by_id or target_id not in state.entities_by_id:
            return None
        if source_id == target_id:
            return None

        key = (source_id, relationship, target_id)
        existing = state.relationships_by_key.get(key)
        if existing is not None:
            for ref in (evidence_refs or []):
                if isinstance(ref, str) and ref and ref not in existing.evidence_refs:
                    if len(existing.evidence_refs) < self.limits.max_evidence_refs_per_entity:
                        existing.evidence_refs.append(ref)
            if source_relationship_id:
                merged = existing.properties.setdefault("merged_source_relationship_ids", [])
                if (
                    source_relationship_id != existing.source_relationship_id
                    and source_relationship_id not in merged
                ):
                    merged.append(source_relationship_id)
                    merged.sort()
            if derivation and derivation != existing.derivation:
                merged = existing.properties.setdefault("merged_derivations", [])
                if derivation not in merged:
                    merged.append(derivation)
                    merged.sort()
            return existing

        if len(state.relationships) >= self.limits.max_relationships:
            state.warn(
                f"max_relationships limit ({self.limits.max_relationships}) reached; further "
                "relationships were not added."
            )
            return None

        if status == INFERRED and not inference_reason:
            # Structural edges must explain themselves; fall back to the
            # derivation rather than emitting a bare, unexplained inference.
            inference_reason = (
                f"Derived from {derivation}." if derivation
                else "Derived from the unified application model without a recorded reason."
            )

        rel = KnowledgeRelationship(
            id=relationship_id(source_id, relationship, target_id),
            source_id=source_id,
            relationship=relationship,
            target_id=target_id,
            status=status if status in (OBSERVED, INFERRED, UNKNOWN) else UNKNOWN,
            confidence=confidence,
            confidence_basis=confidence_basis,
            inference_reason=inference_reason,
            evidence_refs=self._refs(evidence_refs),
            source_relationship_id=source_relationship_id,
            derivation_kind=derivation_kind,
            derivation=derivation,
        )
        state.relationships.append(rel)
        state.relationships_by_key[key] = rel
        return rel

    # -- pass 3a: translate Phase 1.5F relationships (§20) ------------------

    def _translate_unified_relationships(self, state: _BuildState, data: Dict[str, Any]) -> None:
        for rel in self._collection(data, "relationships"):
            source_uid = str(rel.get("source_id") or "")
            target_uid = str(rel.get("target_id") or "")
            source_kid = state.uid_to_kid.get(source_uid)
            target_kid = state.uid_to_kid.get(target_uid)
            if not source_kid or not target_kid:
                state.warn(
                    f"Unified relationship '{rel.get('id')}' references an entity that is not "
                    "present in the knowledge model and was skipped."
                )
                continue

            source_type = state.uid_to_type.get(source_uid, "")
            target_type = state.uid_to_type.get(target_uid, "")
            mapped, invert = self._map_relationship_type(
                str(rel.get("relationship") or ""), source_type, target_type, state
            )
            if mapped is None:
                continue

            a, b = (target_kid, source_kid) if invert else (source_kid, target_kid)
            derivation = (
                f"Inverted from UnifiedApplicationModel.relationships "
                f"('{rel.get('relationship')}' {source_uid} -> {target_uid}) so that the "
                "knowledge graph reads parent-to-child."
                if invert
                else f"UnifiedApplicationModel.relationships ('{rel.get('relationship')}')"
            )
            self._add_relationship(
                state,
                a,
                mapped,
                b,
                self._status(rel),
                confidence=rel.get("confidence"),
                confidence_basis=rel.get("confidence_basis"),
                inference_reason=rel.get("inference_reason"),
                evidence_refs=rel.get("evidence_refs"),
                source_relationship_id=rel.get("id"),
                derivation_kind=DERIVATION_TRANSLATED,
                derivation=derivation,
            )

    def _map_relationship_type(
        self, unified_type: str, source_type: str, target_type: str, state: _BuildState
    ) -> Tuple[Optional[str], bool]:
        """
        Map a Phase 1.5F relationship onto the knowledge vocabulary.

        Returns ``(knowledge_relationship, invert_direction)``.

        The refinement of a generic ``contains`` into ``has_control`` /
        ``has_form`` / ``has_field`` is decided purely by the endpoint entity
        types, so it is deterministic and adds no inference.
        """
        if unified_type == "contains":
            if source_type == ENTITY_PAGE and target_type == ENTITY_CONTROL:
                return HAS_CONTROL, False
            if source_type == ENTITY_PAGE and target_type == ENTITY_FORM:
                return HAS_FORM, False
            if source_type == ENTITY_FORM and target_type == ENTITY_CONTROL:
                return HAS_FIELD, False
            return CONTAINS, False

        if unified_type == "belongs_to":
            # page belongs_to module is stored the other way round so the graph
            # reads application -> module -> page (§22).
            if source_type == ENTITY_PAGE and target_type == ENTITY_MODULE:
                return CONTAINS, True
            return BELONGS_TO, False

        if unified_type == "rendered_on":
            return OBSERVED_ON, False
        if unified_type == "observed_with":
            if source_type == ENTITY_API_ENDPOINT and target_type == ENTITY_PAGE:
                return OBSERVED_ON, False
            return ASSOCIATED_WITH, False
        if unified_type == "submits_to":
            return SUBMITS_TO, False
        if unified_type == "likely_triggers":
            return LIKELY_TRIGGERS, False
        if unified_type == "navigates_to":
            return NAVIGATES_TO, False
        if unified_type == "satisfies":
            return SATISFIES, False
        if unified_type == "associated_with":
            return ASSOCIATED_WITH, False
        if unified_type == "labels":
            return ASSOCIATED_WITH, False
        if unified_type == "implements":
            return IMPLEMENTED_BY, False

        state.warn(
            f"Unified relationship type '{unified_type}' has no knowledge-vocabulary mapping; "
            "it was recorded as 'associated_with'."
        )
        return ASSOCIATED_WITH, False

    def _inherited_status(
        self,
        state: _BuildState,
        source_uid: Any,
        target_uid: Any,
        unified_types: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Find the Phase 1.5F relationship backing a structural edge, in either
        direction, so the edge can inherit an honest status instead of assuming
        one. Returns ``None`` when Phase 1.5F recorded nothing.
        """
        for key in ((str(source_uid or ""), str(target_uid or "")),
                    (str(target_uid or ""), str(source_uid or ""))):
            for rel in state.unified_edges.get(key, []):
                if rel.get("relationship") in unified_types:
                    return rel
        return None

    # -- pass 3b: structural relationships ---------------------------------

    def _build_structural_relationships(self, state: _BuildState, data: Dict[str, Any]) -> None:
        self._link_application(state, data)
        self._link_modules(state, data)
        self._link_pages(state, data)
        self._link_forms(state, data)
        self._link_flows(state, data)
        self._link_repository(state, data)

    def _link_application(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """Link the application to its modules, pages, endpoints, requirements
        and technologies (§10)."""
        app_id = state.application_entity_id
        if not app_id:
            return
        app_entity = state.entities_by_id.get(app_id)
        app_refs = app_entity.evidence_refs if app_entity else []

        for source_key, entity_type in (
            ("modules", ENTITY_MODULE),
            ("pages", ENTITY_PAGE),
            ("api_endpoints", ENTITY_API_ENDPOINT),
        ):
            for item in self._collection(data, source_key):
                kid = state.uid_to_kid.get(str(item.get("id") or ""))
                target = state.entities_by_id.get(kid or "")
                if target is None:
                    continue
                self._add_relationship(
                    state, app_id, CONTAINS, kid,
                    weakest_status(target.status),
                    inference_reason=target.inference_reason,
                    evidence_refs=target.evidence_refs[:3],
                    derivation=f"UnifiedApplicationModel.{source_key}",
                )

        # A supplied requirement is associated with the application as a matter
        # of input, which is an observed fact. Whether it is *satisfied* is a
        # separate, always-inferred claim carried by `satisfies` edges (§17).
        for item in self._collection(data, "requirements"):
            kid = state.uid_to_kid.get(str(item.get("id") or ""))
            if not kid:
                continue
            self._add_relationship(
                state, app_id, ASSOCIATED_WITH, kid, OBSERVED,
                evidence_refs=self._refs(item.get("evidence_refs")),
                derivation="UnifiedApplicationModel.requirements",
            )

        for entity in list(state.entities):
            if entity.entity_type != ENTITY_TECHNOLOGY:
                continue
            self._add_relationship(
                state, app_id, USES, entity.id, INFERRED,
                inference_reason=entity.inference_reason,
                evidence_refs=entity.evidence_refs,
                derivation="UnifiedApplicationModel.application.technology_stack",
            )

    def _link_modules(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """Module -> page / control / form / api_endpoint (§11, §22)."""
        for item in self._collection(data, "modules"):
            module_uid = str(item.get("id") or "")
            module_kid = state.uid_to_kid.get(module_uid)
            module_entity = state.entities_by_id.get(module_kid or "")
            if module_entity is None:
                continue
            reason = item.get("inference_reason") or (
                f"Listed as a member of module '{module_entity.display_name}' by Phase 1.5F "
                "evidence fusion."
            )
            for source_key in ("pages", "controls", "forms", "api_endpoints"):
                for member_uid in (item.get(source_key) or []):
                    member_kid = state.uid_to_kid.get(str(member_uid))
                    member = state.entities_by_id.get(member_kid or "")
                    if member is None:
                        continue
                    self._add_relationship(
                        state, module_kid, CONTAINS, member_kid,
                        weakest_status(module_entity.status, member.status),
                        inference_reason=reason,
                        evidence_refs=module_entity.evidence_refs[:3],
                        derivation=f"UnifiedModule.{source_key}",
                    )

    def _link_pages(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """
        Page -> control / form, and api_endpoint -> page.

        These normally already exist from the translation pass; emitting them
        again from the membership lists guarantees the graph stays complete even
        if Phase 1.5F hit its ``max_relationships`` cap and dropped edges.
        """
        for item in self._collection(data, "pages"):
            page_uid = str(item.get("id") or "")
            page_kid = state.uid_to_kid.get(page_uid)
            page_entity = state.entities_by_id.get(page_kid or "")
            if page_entity is None:
                continue

            for source_key, rel_type, unified_types in (
                ("controls", HAS_CONTROL, ("contains",)),
                ("forms", HAS_FORM, ("contains",)),
            ):
                for member_uid in (item.get(source_key) or []):
                    member_kid = state.uid_to_kid.get(str(member_uid))
                    member = state.entities_by_id.get(member_kid or "")
                    if member is None:
                        continue
                    backing = self._inherited_status(state, page_uid, member_uid, unified_types)
                    self._add_relationship(
                        state, page_kid, rel_type, member_kid,
                        self._status(backing) if backing else INFERRED,
                        inference_reason=(
                            (backing or {}).get("inference_reason")
                            or (
                                None if backing else
                                f"Listed in UnifiedPage.{source_key}; Phase 1.5F recorded no "
                                "explicit containment relationship for this member."
                            )
                        ),
                        evidence_refs=(backing or {}).get("evidence_refs") or member.evidence_refs[:3],
                        source_relationship_id=(backing or {}).get("id"),
                        derivation=f"UnifiedPage.{source_key}",
                    )

            for api_uid in (item.get("api_endpoints") or []):
                api_kid = state.uid_to_kid.get(str(api_uid))
                api_entity = state.entities_by_id.get(api_kid or "")
                if api_entity is None:
                    continue
                backing = self._inherited_status(state, api_uid, page_uid, ("observed_with",))
                self._add_relationship(
                    state, api_kid, OBSERVED_ON, page_kid,
                    self._status(backing) if backing else OBSERVED,
                    inference_reason=(backing or {}).get("inference_reason"),
                    evidence_refs=(backing or {}).get("evidence_refs") or api_entity.evidence_refs[:3],
                    source_relationship_id=(backing or {}).get("id"),
                    derivation="UnifiedPage.api_endpoints",
                )

    def _link_forms(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """Form -> field / submit control / endpoint (§14)."""
        for item in self._collection(data, "forms"):
            form_uid = str(item.get("id") or "")
            form_kid = state.uid_to_kid.get(form_uid)
            form_entity = state.entities_by_id.get(form_kid or "")
            if form_entity is None:
                continue

            for field_uid in (item.get("fields") or []):
                field_kid = state.uid_to_kid.get(str(field_uid))
                field_entity = state.entities_by_id.get(field_kid or "")
                if field_entity is None:
                    continue
                backing = self._inherited_status(state, form_uid, field_uid, ("contains",))
                self._add_relationship(
                    state, form_kid, HAS_FIELD, field_kid,
                    self._status(backing) if backing else INFERRED,
                    inference_reason=(
                        (backing or {}).get("inference_reason")
                        or (None if backing else "Listed in UnifiedForm.fields.")
                    ),
                    evidence_refs=(backing or {}).get("evidence_refs") or field_entity.evidence_refs[:3],
                    source_relationship_id=(backing or {}).get("id"),
                    derivation="UnifiedForm.fields",
                )

            submit_uid = item.get("submit_control")
            submit_kid = state.uid_to_kid.get(str(submit_uid or ""))
            if submit_kid and submit_kid in state.entities_by_id:
                # Phase 1.5F may itself have only *inferred* that this control
                # submits the form, so the status is inherited rather than
                # assumed observed (§32).
                backing = self._inherited_status(state, submit_uid, form_uid, ("belongs_to",))
                self._add_relationship(
                    state, form_kid, HAS_CONTROL, submit_kid,
                    self._status(backing) if backing else INFERRED,
                    inference_reason=(
                        (backing or {}).get("inference_reason")
                        or (
                            None if backing else
                            "Identified as the form's submit control by Phase 1.5F form fusion; "
                            "no submission was executed."
                        )
                    ),
                    evidence_refs=(backing or {}).get("evidence_refs")
                    or state.entities_by_id[submit_kid].evidence_refs[:3],
                    source_relationship_id=(backing or {}).get("id"),
                    derivation="UnifiedForm.submit_control",
                )

            for api_uid in (item.get("observed_api_endpoints") or []):
                api_kid = state.uid_to_kid.get(str(api_uid))
                if not api_kid or api_kid not in state.entities_by_id:
                    continue
                backing = self._inherited_status(state, form_uid, api_uid, ("submits_to",))
                if backing is None:
                    # Without a Phase 1.5F submits_to edge there is no evidence
                    # that this form submits here; record the weaker claim only.
                    self._add_relationship(
                        state, form_kid, ASSOCIATED_WITH, api_kid, INFERRED,
                        inference_reason=(
                            "Listed in UnifiedForm.observed_api_endpoints. Phase 1.5F recorded no "
                            "submits_to relationship, so no submission is claimed."
                        ),
                        evidence_refs=form_entity.evidence_refs[:3],
                        derivation="UnifiedForm.observed_api_endpoints",
                    )
                else:
                    self._add_relationship(
                        state, form_kid, SUBMITS_TO, api_kid, self._status(backing),
                        confidence=backing.get("confidence"),
                        confidence_basis=backing.get("confidence_basis"),
                        inference_reason=backing.get("inference_reason"),
                        evidence_refs=backing.get("evidence_refs"),
                        source_relationship_id=backing.get("id"),
                        derivation="UnifiedForm.observed_api_endpoints",
                    )

    def _link_flows(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """Flow -> starting page / controls / endpoints / further pages (§16)."""
        for item in self._collection(data, "user_flows"):
            flow_kid = state.uid_to_kid.get(str(item.get("id") or ""))
            flow_entity = state.entities_by_id.get(flow_kid or "")
            if flow_entity is None:
                continue
            reason = item.get("inference_reason") or (
                f"Member of user flow '{flow_entity.display_name}' as assembled by Phase 1.5F."
            )
            steps = flow_entity.properties.get("steps") or []

            # starts_at: the first step, when it is a navigation.
            start_page_id: Optional[str] = None
            for step in steps:
                if step.get("action") == "navigate" and step.get("page_id"):
                    start_page_id = step["page_id"]
                    self._add_relationship(
                        state, flow_kid, STARTS_AT, start_page_id,
                        step.get("observation_status") or INFERRED,
                        inference_reason=step.get("inference_reason"),
                        evidence_refs=step.get("evidence_refs"),
                        derivation="UnifiedUserFlow.steps (first navigate step)",
                    )
                    break
            if start_page_id is None:
                page_ids = flow_entity.properties.get("page_ids") or []
                if page_ids:
                    start_page_id = page_ids[0]
                    self._add_relationship(
                        state, flow_kid, STARTS_AT, start_page_id,
                        weakest_status(flow_entity.status), inference_reason=reason,
                        evidence_refs=flow_entity.evidence_refs[:3],
                        derivation="UnifiedUserFlow.page_ids[0]",
                    )

            for control_id in (flow_entity.properties.get("control_ids") or []):
                control = state.entities_by_id.get(control_id)
                if control is None:
                    continue
                self._add_relationship(
                    state, flow_kid, USES, control_id,
                    weakest_status(flow_entity.status, control.status),
                    inference_reason=reason,
                    evidence_refs=flow_entity.evidence_refs[:3],
                    derivation="UnifiedUserFlow.control_ids",
                )

            for api_id in (flow_entity.properties.get("api_endpoint_ids") or []):
                api_entity = state.entities_by_id.get(api_id)
                if api_entity is None:
                    continue
                self._add_relationship(
                    state, flow_kid, CALLS, api_id,
                    weakest_status(flow_entity.status, api_entity.status),
                    inference_reason=reason,
                    evidence_refs=flow_entity.evidence_refs[:3],
                    derivation="UnifiedUserFlow.api_endpoint_ids",
                )

            # navigates_to only for pages beyond the start: the crawler never
            # executed the flow, so no transition is invented (§16).
            for page_id in (flow_entity.properties.get("page_ids") or []):
                if page_id == start_page_id or page_id not in state.entities_by_id:
                    continue
                self._add_relationship(
                    state, flow_kid, NAVIGATES_TO, page_id,
                    weakest_status(flow_entity.status), inference_reason=reason,
                    evidence_refs=flow_entity.evidence_refs[:3],
                    derivation="UnifiedUserFlow.page_ids",
                )

    def _link_repository(self, state: _BuildState, data: Dict[str, Any]) -> None:
        """Entity -> repository_file, and file -> symbol (§18)."""
        for uid, source in state.uid_to_source.items():
            kid = state.uid_to_kid.get(uid)
            entity = state.entities_by_id.get(kid or "")
            if entity is None:
                continue
            for ref in (source.get("repository_refs") or []):
                if not isinstance(ref, dict):
                    continue
                path = normalize_path(ref.get("file"))
                if not path:
                    continue
                file_id = f"repo:file:{path}"
                if file_id not in state.entities_by_id:
                    continue
                self._add_relationship(
                    state, kid, IMPLEMENTED_BY, file_id, INFERRED,
                    inference_reason=(
                        f"Phase 1.5F repository analysis matched this entity to {path} because the "
                        f"{ref.get('match_reason') or 'filename matched'}. The file was not "
                        "parsed, so the implementation link is not confirmed."
                    ),
                    evidence_refs=[ref["evidence_ref"]] if ref.get("evidence_ref") else None,
                    derivation=f"{entity.entity_type}.repository_refs",
                )

        for entity in list(state.entities):
            if entity.entity_type != ENTITY_REPOSITORY_FILE:
                continue
            path = entity.properties.get("path")
            for symbol in (entity.properties.get("symbols") or []):
                symbol_id = f"repo:symbol:{path}:{symbol}"
                if symbol_id not in state.entities_by_id:
                    continue
                self._add_relationship(
                    state, entity.id, CONTAINS, symbol_id, INFERRED,
                    inference_reason=(
                        "Symbol name derived from the file name by Phase 1.5F repository "
                        "analysis; the file was not parsed."
                    ),
                    evidence_refs=entity.evidence_refs[:2],
                    derivation="repository_refs.symbol",
                )


__all__ = [
    "DeterministicApplicationKnowledgeBuilder",
    "KnowledgeLimits",
]
