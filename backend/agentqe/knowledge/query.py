"""
Phase 1.5G — Deterministic, read-only query layer (§25, §26, §30, §31, §46).

Everything in this module is exact-match: dictionary lookups, list filters, and
substring matching on names that were already normalized at build time. There
is no embedding, no vector store, no similarity scoring, no LLM and no network
access (§27, §28).

Every method is side-effect free and returns plain JSON-safe dicts, so the same
call on the same model always produces the same answer.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from agentqe.knowledge.index import KnowledgeIndex
from agentqe.knowledge.interfaces import ApplicationKnowledgeQuery
from agentqe.knowledge.knowledge_model import KnowledgeGraph
from agentqe.knowledge.schemas import (
    ASSOCIATED_WITH,
    CALLS,
    CONTAINS,
    ENTITY_API_ENDPOINT,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REQUIREMENT,
    ENTITY_TECHNOLOGY,
    ENTITY_USER_FLOW,
    HAS_CONTROL,
    HAS_FIELD,
    IMPLEMENTED_BY,
    NAVIGATES_TO,
    OBSERVED,
    SATISFIES,
    STARTS_AT,
    SUBMITS_TO,
    USES,
    ApplicationKnowledgeModel,
    KnowledgeEntity,
    KnowledgeRelationship,
)

#: Hard ceiling on any single list a query returns, so a UI or a future RAG
#: retriever cannot accidentally pull the whole graph in one call (§26).
DEFAULT_RESULT_LIMIT = 500


class DeterministicKnowledgeQuery(ApplicationKnowledgeQuery):
    """Read-only query surface over one ``ApplicationKnowledgeModel``."""

    def __init__(
        self,
        model: ApplicationKnowledgeModel,
        index: Optional[KnowledgeIndex] = None,
        result_limit: int = DEFAULT_RESULT_LIMIT,
    ) -> None:
        self.model = model
        self.index = index or KnowledgeIndex.build(model)
        self.graph = KnowledgeGraph(model, self.index)
        self.result_limit = result_limit

    # -- helpers ------------------------------------------------------------

    def _entity_dict(self, entity: Optional[KnowledgeEntity]) -> Optional[Dict[str, Any]]:
        return entity.to_dict() if entity is not None else None

    def _entity_dicts(self, entities: Iterable[KnowledgeEntity]) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in list(entities)[: self.result_limit]]

    def _rel_dicts(self, rels: Iterable[KnowledgeRelationship]) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in list(rels)[: self.result_limit]]

    def _brief(self, entity_id: str) -> Dict[str, Any]:
        """A compact node reference for context payloads (§30)."""
        entity = self.index.entities_by_id.get(entity_id)
        if entity is None:
            return {"id": entity_id, "entity_type": None, "name": None, "status": None,
                    "resolved": False}
        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.display_name or entity.name,
            "status": entity.status,
            "resolved": True,
        }

    def _briefs(self, entity_ids: Iterable[str]) -> List[Dict[str, Any]]:
        return [self._brief(eid) for eid in list(entity_ids)[: self.result_limit]]

    def _resolve(self, entity_id: str, expected_type: Optional[str] = None) -> Optional[KnowledgeEntity]:
        resolved = self.index.resolve(entity_id)
        if not resolved:
            return None
        entity = self.index.entities_by_id.get(resolved)
        if entity is None:
            return None
        if expected_type and entity.entity_type != expected_type:
            return None
        return entity

    # =====================================================================
    # 1-5: entity access
    # =====================================================================

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(entity_id))

    def get_entities_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        return self._entity_dicts(self.index.of_type(entity_type))

    def find_entities(
        self,
        entity_type: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """AND semantics across every supplied filter. ``name`` is a
        case-insensitive substring match on the display name."""
        candidates = (
            self.index.of_type(entity_type) if entity_type
            else list(self.model.entities or [])
        )
        needle = name.strip().lower() if isinstance(name, str) and name.strip() else None
        out: List[KnowledgeEntity] = []
        for entity in candidates:
            if status and entity.status != status:
                continue
            if needle:
                haystack = f"{entity.display_name} {entity.name} {entity.canonical_name}".lower()
                if needle not in haystack:
                    continue
            out.append(entity)
        return self._entity_dicts(out)

    def search_entities(self, text: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Exact-then-substring name search.

        Deliberately lexical: Phase 1.5G must not use embeddings or semantic
        similarity (§27). Exact name matches are returned first, then substring
        matches, then id matches — a stable, explainable ordering.
        """
        needle = (text or "").strip().lower()
        if not needle:
            return []
        seen: List[str] = []

        for entity_id in self.index.entities_by_name.get(needle, []):
            if entity_id not in seen:
                seen.append(entity_id)

        for entity in (self.model.entities or []):
            if len(seen) >= limit:
                break
            if entity.id in seen:
                continue
            haystack = f"{entity.display_name} {entity.name} {entity.canonical_name}".lower()
            if needle in haystack:
                seen.append(entity.id)

        for entity in (self.model.entities or []):
            if len(seen) >= limit:
                break
            if entity.id not in seen and needle in entity.id.lower():
                seen.append(entity.id)

        return [
            self.index.entities_by_id[eid].to_dict()
            for eid in seen[:limit]
            if eid in self.index.entities_by_id
        ]

    # =====================================================================
    # 6-8: relationship access
    # =====================================================================

    def find_relationships(
        self,
        source_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if source_id:
            pool = self.index.outgoing(self.index.resolve(source_id) or source_id)
        elif target_id:
            pool = self.index.incoming(self.index.resolve(target_id) or target_id)
        elif relationship_type:
            pool = self.index.of_relationship_type(relationship_type)
        else:
            pool = list(self.model.relationships or [])

        resolved_target = self.index.resolve(target_id) if target_id else None
        out = []
        for rel in pool:
            if relationship_type and rel.relationship != relationship_type:
                continue
            if target_id and rel.target_id != (resolved_target or target_id):
                continue
            out.append(rel)
        return self._rel_dicts(out)

    def get_relationships_for_entity(self, entity_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Both directions, kept separate so a caller can tell them apart."""
        resolved = self.index.resolve(entity_id) or entity_id
        return {
            "outgoing": self._rel_dicts(self.index.outgoing(resolved)),
            "incoming": self._rel_dicts(self.index.incoming(resolved)),
        }

    def get_neighbors(self, entity_id: str) -> List[Dict[str, Any]]:
        resolved = self.index.resolve(entity_id) or entity_id
        out: List[Dict[str, Any]] = []
        for edge in self.graph.edges_of(resolved)[: self.result_limit]:
            other_id = edge.target_id if edge.direction == "outgoing" else edge.source_id
            rel = self.index.relationships_by_id.get(edge.relationship_id)
            out.append({
                "entity": self._brief(other_id),
                "relationship": edge.relationship,
                "direction": edge.direction,
                "relationship_id": edge.relationship_id,
                "status": rel.status if rel else None,
                "inference_reason": rel.inference_reason if rel else None,
            })
        return out

    def get_subgraph(
        self, entity_id: str, depth: int = 1, max_nodes: int = 60
    ) -> Dict[str, Any]:
        """Bounded neighbourhood, for the optional UI graph view (§44)."""
        resolved = self.index.resolve(entity_id) or entity_id
        return self.graph.subgraph(resolved, depth=depth, max_nodes=max_nodes)

    # =====================================================================
    # 9-14: page / control / form / api access
    # =====================================================================

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(page_id, ENTITY_PAGE))

    def get_page_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        page_id = self.index.pages_by_url.get(url)
        if not page_id:
            return None
        return self._entity_dict(self.index.entities_by_id.get(page_id))

    def get_controls_for_page(self, page_id: str) -> List[Dict[str, Any]]:
        page = self._resolve(page_id, ENTITY_PAGE)
        if page is None:
            return []
        return self._entity_dicts(
            e for e in (
                self.index.entities_by_id.get(cid)
                for cid in self.index.controls_by_page.get(page.id, [])
            ) if e is not None
        )

    def get_forms_for_page(self, page_id: str) -> List[Dict[str, Any]]:
        page = self._resolve(page_id, ENTITY_PAGE)
        if page is None:
            return []
        return self._entity_dicts(
            e for e in (
                self.index.entities_by_id.get(fid)
                for fid in self.index.forms_by_page.get(page.id, [])
            ) if e is not None
        )

    def get_apis_for_page(self, page_id: str) -> List[Dict[str, Any]]:
        page = self._resolve(page_id, ENTITY_PAGE)
        if page is None:
            return []
        return self._entity_dicts(
            e for e in (
                self.index.entities_by_id.get(aid)
                for aid in self.index.apis_by_page.get(page.id, [])
            ) if e is not None
        )

    def get_form(self, form_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(form_id, ENTITY_FORM))

    def get_fields_for_form(self, form_id: str) -> List[Dict[str, Any]]:
        form = self._resolve(form_id, ENTITY_FORM)
        if form is None:
            return []
        field_ids = [
            rel.target_id for rel in self.index.outgoing(form.id)
            if rel.relationship == HAS_FIELD
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(fid) for fid in field_ids) if e is not None
        )

    def get_apis_for_form(self, form_id: str) -> List[Dict[str, Any]]:
        form = self._resolve(form_id, ENTITY_FORM)
        if form is None:
            return []
        api_ids = [
            rel.target_id for rel in self.index.outgoing(form.id)
            if rel.relationship in (SUBMITS_TO, ASSOCIATED_WITH)
            and self.index.entities_by_id.get(rel.target_id, KnowledgeEntity("", "")).entity_type
            == ENTITY_API_ENDPOINT
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(aid) for aid in api_ids) if e is not None
        )

    def get_control(self, control_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(control_id, ENTITY_CONTROL))

    def get_api(self, api_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(api_id, ENTITY_API_ENDPOINT))

    # =====================================================================
    # 15-18: module / flow / requirement / repository access
    # =====================================================================

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(module_id, ENTITY_MODULE))

    def get_modules_for_entity(self, entity_id: str) -> List[Dict[str, Any]]:
        """Modules that ``contains`` this entity."""
        resolved = self.index.resolve(entity_id)
        if not resolved:
            return []
        module_ids = [
            rel.source_id for rel in self.index.incoming(resolved)
            if rel.relationship == CONTAINS
            and self.index.entities_by_id.get(rel.source_id, KnowledgeEntity("", "")).entity_type
            == ENTITY_MODULE
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(mid) for mid in module_ids) if e is not None
        )

    def get_flow(self, flow_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(flow_id, ENTITY_USER_FLOW))

    def get_flows_for_page(self, page_id: str) -> List[Dict[str, Any]]:
        page = self._resolve(page_id, ENTITY_PAGE)
        if page is None:
            return []
        flow_ids: List[str] = []
        for rel in self.index.incoming(page.id):
            if rel.relationship not in (STARTS_AT, NAVIGATES_TO):
                continue
            source = self.index.entities_by_id.get(rel.source_id)
            if source is not None and source.entity_type == ENTITY_USER_FLOW:
                if source.id not in flow_ids:
                    flow_ids.append(source.id)
        return self._entity_dicts(self.index.entities_by_id[f] for f in flow_ids)

    def get_requirement(self, requirement_id: str) -> Optional[Dict[str, Any]]:
        return self._entity_dict(self._resolve(requirement_id, ENTITY_REQUIREMENT))

    def get_requirements_for_entity(self, entity_id: str) -> List[Dict[str, Any]]:
        resolved = self.index.resolve(entity_id)
        if not resolved:
            return []
        requirement_ids = [
            rel.target_id for rel in self.index.outgoing(resolved)
            if rel.relationship == SATISFIES
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(r) for r in requirement_ids) if e is not None
        )

    def get_entities_for_requirement(self, requirement_id: str) -> List[Dict[str, Any]]:
        requirement = self._resolve(requirement_id, ENTITY_REQUIREMENT)
        if requirement is None:
            return []
        source_ids = [
            rel.source_id for rel in self.index.incoming(requirement.id)
            if rel.relationship == SATISFIES
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(s) for s in source_ids) if e is not None
        )

    def get_repository_files_for_entity(self, entity_id: str) -> List[Dict[str, Any]]:
        resolved = self.index.resolve(entity_id)
        if not resolved:
            return []
        file_ids = [
            rel.target_id for rel in self.index.outgoing(resolved)
            if rel.relationship == IMPLEMENTED_BY
        ]
        return self._entity_dicts(
            e for e in (self.index.entities_by_id.get(f) for f in file_ids) if e is not None
        )

    def get_technologies(self) -> List[Dict[str, Any]]:
        return self._entity_dicts(self.index.of_type(ENTITY_TECHNOLOGY))

    def get_statistics(self) -> Dict[str, Any]:
        """The summary block, plus index sizes — never the graph itself."""
        summaries = self.model.summaries or {}
        return {
            "application_summary": summaries.get("application_summary", {}),
            "entity_count": len(self.model.entities or []),
            "relationship_count": len(self.model.relationships or []),
            "entities_by_type": self.index.counts(),
            "index_sizes": {
                "pages_by_url": len(self.index.pages_by_url),
                "controls_by_page": len(self.index.controls_by_page),
                "forms_by_page": len(self.index.forms_by_page),
                "apis_by_page": len(self.index.apis_by_page),
                "relationships_by_source": len(self.index.relationships_by_source),
                "relationships_by_target": len(self.index.relationships_by_target),
            },
            "model_version": self.model.model_version,
            "provenance": self.model.provenance.to_dict() if self.model.provenance else {},
        }

    # =====================================================================
    # Higher-level context queries (§26, §30, §31)
    # =====================================================================

    def get_page_context(self, page_id: str) -> Dict[str, Any]:
        """
        Everything a test generator needs about one page, and nothing more (§30).

        Contains no raw DOM, no accessibility tree, no network body and no
        screenshot bytes — only references (``screenshot_ref``, ``dom_ref``,
        ``evidence_refs``).
        """
        page = self._resolve(page_id, ENTITY_PAGE)
        if page is None:
            return {"found": False, "page_id": page_id}

        props = page.properties or {}
        controls = [
            self.index.entities_by_id[c]
            for c in self.index.controls_by_page.get(page.id, [])
            if c in self.index.entities_by_id
        ]
        forms = [
            self.index.entities_by_id[f]
            for f in self.index.forms_by_page.get(page.id, [])
            if f in self.index.entities_by_id
        ]
        apis = [
            self.index.entities_by_id[a]
            for a in self.index.apis_by_page.get(page.id, [])
            if a in self.index.entities_by_id
        ]

        return {
            "found": True,
            "page": {
                "id": page.id,
                "name": page.display_name,
                "url": props.get("url"),
                "normalized_url": props.get("normalized_url"),
                "title": props.get("title"),
                "page_type": props.get("page_type"),
                "page_type_status": props.get("page_type_status"),
                "depth": props.get("depth"),
                "status": page.status,
                "screenshot_ref": props.get("screenshot_ref"),
                "crawl_ref": props.get("crawl_ref"),
                "visual_ui_status": props.get("visual_ui_status"),
                "evidence_refs": list(page.evidence_refs),
                "evidence_sources": list(page.evidence_sources),
            },
            "controls": [self._control_brief(c) for c in controls[: self.result_limit]],
            "forms": [self._form_brief(f) for f in forms[: self.result_limit]],
            "api_endpoints": [self._api_brief(a) for a in apis[: self.result_limit]],
            "modules": self.get_modules_for_entity(page.id),
            "flows": [self._brief(f["id"]) for f in self.get_flows_for_page(page.id)],
            "requirements": [self._brief(r) for r in (page.requirement_refs or [])],
            "repository_files": [
                self._brief(r["id"]) for r in self.get_repository_files_for_entity(page.id)
            ],
            "relationships": self.get_relationships_for_entity(page.id),
            "counts": {
                "controls": len(controls),
                "forms": len(forms),
                "api_endpoints": len(apis),
                "observed_controls": sum(1 for c in controls if c.status == OBSERVED),
            },
        }

    def get_control_context(self, control_id: str) -> Dict[str, Any]:
        """One control, its page, its form, and what it is believed to trigger (§26)."""
        control = self._resolve(control_id, ENTITY_CONTROL)
        if control is None:
            return {"found": False, "control_id": control_id}

        props = control.properties or {}
        triggers = [
            {
                "entity": self._brief(rel.target_id),
                "relationship": rel.relationship,
                "status": rel.status,
                "confidence": rel.confidence,
                "confidence_basis": rel.confidence_basis,
                "inference_reason": rel.inference_reason,
            }
            for rel in self.index.outgoing(control.id)
            if rel.relationship in (SUBMITS_TO, "likely_triggers", NAVIGATES_TO, CALLS)
        ]

        return {
            "found": True,
            "control": self._control_brief(control),
            "page": self._brief(props.get("page_id")) if props.get("page_id") else None,
            "form": self._brief(props.get("form_id")) if props.get("form_id") else None,
            "modules": self.get_modules_for_entity(control.id),
            "triggers": triggers,
            "requirements": [self._brief(r) for r in (control.requirement_refs or [])],
            "repository_files": [
                self._brief(r["id"]) for r in self.get_repository_files_for_entity(control.id)
            ],
            "relationships": self.get_relationships_for_entity(control.id),
        }

    def get_flow_context(self, flow_id: str) -> Dict[str, Any]:
        """
        A flow with its steps resolved to entities, in order (§31).

        Each step keeps its own ``observation_status`` so the caller can tell a
        navigation that really happened from a click that was never executed.
        """
        flow = self._resolve(flow_id, ENTITY_USER_FLOW)
        if flow is None:
            return {"found": False, "flow_id": flow_id}

        props = flow.properties or {}
        steps = []
        for step in (props.get("steps") or []):
            enriched = dict(step)
            enriched["entity"] = self._brief(step["entity_id"]) if step.get("entity_id") else None
            steps.append(enriched)

        start = [rel.target_id for rel in self.index.outgoing(flow.id) if rel.relationship == STARTS_AT]

        return {
            "found": True,
            "flow": {
                "id": flow.id,
                "name": flow.display_name,
                "source": props.get("source"),
                "semantic_role": props.get("semantic_role"),
                "status": flow.status,
                "confidence": flow.confidence,
                "confidence_basis": flow.confidence_basis,
                "inference_reason": flow.inference_reason,
                "evidence_refs": list(flow.evidence_refs),
            },
            "starts_at": self._brief(start[0]) if start else None,
            "steps": steps,
            "pages": self._briefs(props.get("page_ids") or []),
            "controls": self._briefs(props.get("control_ids") or []),
            "api_endpoints": self._briefs(props.get("api_endpoint_ids") or []),
            "requirements": [self._brief(r) for r in (flow.requirement_refs or [])],
            "counts": {
                "steps": len(steps),
                "observed_steps": sum(1 for s in steps if s.get("observation_status") == OBSERVED),
            },
        }

    def get_requirement_context(self, requirement_id: str) -> Dict[str, Any]:
        """
        A requirement and what is claimed to satisfy it (§26).

        ``satisfies`` links are keyword-overlap inferences from Phase 1.5F, so
        their status and reason are surfaced rather than presented as coverage.
        """
        requirement = self._resolve(requirement_id, ENTITY_REQUIREMENT)
        if requirement is None:
            return {"found": False, "requirement_id": requirement_id}

        props = requirement.properties or {}
        satisfied_by = [
            {
                "entity": self._brief(rel.source_id),
                "status": rel.status,
                "confidence": rel.confidence,
                "confidence_basis": rel.confidence_basis,
                "inference_reason": rel.inference_reason,
                "evidence_refs": list(rel.evidence_refs),
            }
            for rel in self.index.incoming(requirement.id)
            if rel.relationship == SATISFIES
        ]

        return {
            "found": True,
            "requirement": {
                "id": requirement.id,
                "requirement_id": props.get("requirement_id"),
                "text": props.get("text"),
                "source": props.get("source"),
                "keywords": list(props.get("keywords") or []),
                "status": requirement.status,
                "evidence_refs": list(requirement.evidence_refs),
            },
            "satisfied_by": satisfied_by,
            "counts": {
                "satisfied_by": len(satisfied_by),
                "observed_links": sum(1 for s in satisfied_by if s["status"] == OBSERVED),
            },
        }

    def get_module_context(self, module_id: str) -> Dict[str, Any]:
        module = self._resolve(module_id, ENTITY_MODULE)
        if module is None:
            return {"found": False, "module_id": module_id}
        props = module.properties or {}
        return {
            "found": True,
            "module": {
                "id": module.id,
                "name": module.display_name,
                "source": props.get("source"),
                "status": module.status,
                "inference_reason": module.inference_reason,
                "evidence_refs": list(module.evidence_refs),
            },
            "pages": self._briefs(props.get("page_ids") or []),
            "controls": self._briefs(props.get("control_ids") or []),
            "forms": self._briefs(props.get("form_ids") or []),
            "api_endpoints": self._briefs(props.get("api_endpoint_ids") or []),
            "requirements": [self._brief(r) for r in (module.requirement_refs or [])],
        }

    # =====================================================================
    # Generic retrieval context (§46) — the seam Phase 2 will build on
    # =====================================================================

    def get_context_for_entity(self, entity_id: str) -> Dict[str, Any]:
        """
        Uniform context for any entity type.

        Phase 2 will wrap this to produce retrieval documents, so the output is
        JSON-safe, bounded, and free of raw evidence payloads. It does not call
        an embedding model or a vector store — Phase 1.5G has neither (§27).
        """
        entity = self._resolve(entity_id)
        if entity is None:
            return {"found": False, "entity_id": entity_id}

        specialised: Dict[str, Any] = {}
        if entity.entity_type == ENTITY_PAGE:
            specialised = self.get_page_context(entity.id)
        elif entity.entity_type == ENTITY_CONTROL:
            specialised = self.get_control_context(entity.id)
        elif entity.entity_type == ENTITY_USER_FLOW:
            specialised = self.get_flow_context(entity.id)
        elif entity.entity_type == ENTITY_REQUIREMENT:
            specialised = self.get_requirement_context(entity.id)
        elif entity.entity_type == ENTITY_MODULE:
            specialised = self.get_module_context(entity.id)

        return {
            "found": True,
            "entity": entity.to_dict(),
            "neighbors": self.get_neighbors(entity.id),
            "relationships": self.get_relationships_for_entity(entity.id),
            "provenance": {
                "source_entity_id": entity.source_entity_id,
                "source_entity_type": entity.source_entity_type,
                "evidence_refs": list(entity.evidence_refs),
                "evidence_sources": list(entity.evidence_sources),
                "status": entity.status,
                "confidence": entity.confidence,
                "confidence_basis": entity.confidence_basis,
                "inference_reason": entity.inference_reason,
            },
            "context": specialised,
        }

    # -- compact briefs -----------------------------------------------------

    def _control_brief(self, control: KnowledgeEntity) -> Dict[str, Any]:
        props = control.properties or {}
        return {
            "id": control.id,
            "name": control.display_name,
            "type": props.get("type"),
            "label": props.get("label"),
            "text": props.get("text"),
            "semantic_role": props.get("semantic_role"),
            "semantic_role_status": props.get("semantic_role_status"),
            "interactable": props.get("interactable"),
            "status": control.status,
            "confidence": control.confidence,
            "confidence_basis": control.confidence_basis,
            "inference_reason": control.inference_reason,
            "dom_ref": props.get("dom_ref"),
            "accessibility_ref": props.get("accessibility_ref"),
            "visual_ref": props.get("visual_ref"),
            "dom_id": props.get("dom_id"),
            "dom_tag": props.get("dom_tag"),
            "dom_name": props.get("dom_name"),
            "dom_type": props.get("dom_type"),
            "role": props.get("role"),
            "href": props.get("href"),
            "form_id": props.get("form_id"),
            "evidence_sources": list(control.evidence_sources),
            "evidence_refs": list(control.evidence_refs),
        }

    def _form_brief(self, form: KnowledgeEntity) -> Dict[str, Any]:
        props = form.properties or {}
        return {
            "id": form.id,
            "name": form.display_name,
            "action": props.get("action"),
            "method": props.get("method"),
            "semantic_role": props.get("semantic_role"),
            "semantic_role_status": props.get("semantic_role_status"),
            "status": form.status,
            "field_ids": list(props.get("field_ids") or []),
            "submit_control_id": props.get("submit_control_id"),
            "api_endpoint_ids": list(props.get("api_endpoint_ids") or []),
            "evidence_refs": list(form.evidence_refs),
        }

    def _api_brief(self, api: KnowledgeEntity) -> Dict[str, Any]:
        props = api.properties or {}
        return {
            "id": api.id,
            "name": api.display_name,
            "method": props.get("method"),
            "path": props.get("path"),
            "host": props.get("host"),
            "status": api.status,
            "observation_count": props.get("observation_count"),
            "failure_count": props.get("failure_count"),
            "request_metadata": props.get("request_metadata") or {},
            "response_metadata": props.get("response_metadata") or {},
            "evidence_refs": list(api.evidence_refs),
        }


__all__ = [
    "DeterministicKnowledgeQuery",
    "DEFAULT_RESULT_LIMIT",
]
