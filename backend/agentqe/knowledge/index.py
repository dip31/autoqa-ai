"""
Phase 1.5G — Deterministic indexes over an ``ApplicationKnowledgeModel`` (§24).

Every index here is a plain Python dict built by a single ordered pass over the
model. There is no database, no embedding, no vector store and no similarity
search — lookups are exact-key or exact-filter only (§27, §28).

Serialization note
------------------
``entities_by_id`` and ``relationships_by_id`` hold live objects in memory but
serialize as ``id -> position in the entities/relationships list``. Emitting the
full objects twice would double the payload of every API response for no gain,
and the position map still gives O(1) lookup after ``from_dict`` (§26: "do not
dump the entire graph by default").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentqe.knowledge.schemas import (
    ENTITY_API_ENDPOINT,
    ENTITY_APPLICATION,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REQUIREMENT,
    ENTITY_TECHNOLOGY,
    ENTITY_USER_FLOW,
    ApplicationKnowledgeModel,
    KnowledgeEntity,
    KnowledgeRelationship,
)


@dataclass
class KnowledgeIndex:
    """Exact-match lookup tables over a knowledge model."""

    # -- entity lookups -----------------------------------------------------
    entities_by_id: Dict[str, KnowledgeEntity] = field(default_factory=dict)
    entity_positions: Dict[str, int] = field(default_factory=dict)
    entities_by_type: Dict[str, List[str]] = field(default_factory=dict)
    #: lowercased display name -> entity ids (several entities may share a name)
    entities_by_name: Dict[str, List[str]] = field(default_factory=dict)
    #: Phase 1.5F entity id -> knowledge entity id
    entities_by_source_id: Dict[str, str] = field(default_factory=dict)

    # -- page-centric lookups ----------------------------------------------
    pages_by_url: Dict[str, str] = field(default_factory=dict)
    controls_by_page: Dict[str, List[str]] = field(default_factory=dict)
    forms_by_page: Dict[str, List[str]] = field(default_factory=dict)
    apis_by_page: Dict[str, List[str]] = field(default_factory=dict)

    # -- id-keyed collections ----------------------------------------------
    #: Each maps *both* the original Phase 1.5F / requirement id and the
    #: knowledge id onto the canonical knowledge id, so a caller can resolve an
    #: entity from whichever identifier it happens to be holding.
    requirements_by_id: Dict[str, str] = field(default_factory=dict)
    modules_by_id: Dict[str, str] = field(default_factory=dict)
    flows_by_id: Dict[str, str] = field(default_factory=dict)

    # -- relationship lookups ----------------------------------------------
    relationships_by_id: Dict[str, KnowledgeRelationship] = field(default_factory=dict)
    relationship_positions: Dict[str, int] = field(default_factory=dict)
    relationships_by_source: Dict[str, List[str]] = field(default_factory=dict)
    relationships_by_target: Dict[str, List[str]] = field(default_factory=dict)
    relationships_by_type: Dict[str, List[str]] = field(default_factory=dict)

    # -- construction -------------------------------------------------------

    @classmethod
    def build(cls, model: ApplicationKnowledgeModel) -> "KnowledgeIndex":
        index = cls()

        for position, entity in enumerate(model.entities or []):
            if not isinstance(entity, KnowledgeEntity) or not entity.id:
                continue
            if entity.id in index.entities_by_id:
                continue
            index.entities_by_id[entity.id] = entity
            index.entity_positions[entity.id] = position
            index.entities_by_type.setdefault(entity.entity_type, []).append(entity.id)

            name_key = (entity.display_name or entity.name or "").strip().lower()
            if name_key:
                index.entities_by_name.setdefault(name_key, []).append(entity.id)
            canonical_key = (entity.canonical_name or "").strip().lower()
            if canonical_key and canonical_key != name_key:
                index.entities_by_name.setdefault(canonical_key, []).append(entity.id)

            if entity.source_entity_id:
                index.entities_by_source_id.setdefault(entity.source_entity_id, entity.id)

            index._index_entity_specifics(entity)

        for position, rel in enumerate(model.relationships or []):
            if not isinstance(rel, KnowledgeRelationship) or not rel.id:
                continue
            if rel.id in index.relationships_by_id:
                continue
            index.relationships_by_id[rel.id] = rel
            index.relationship_positions[rel.id] = position
            index.relationships_by_source.setdefault(rel.source_id, []).append(rel.id)
            index.relationships_by_target.setdefault(rel.target_id, []).append(rel.id)
            index.relationships_by_type.setdefault(rel.relationship, []).append(rel.id)

        return index

    def _index_entity_specifics(self, entity: KnowledgeEntity) -> None:
        etype = entity.entity_type
        props = entity.properties or {}

        if etype == ENTITY_PAGE:
            for key in ("url", "normalized_url"):
                value = props.get(key)
                if isinstance(value, str) and value:
                    self.pages_by_url.setdefault(value, entity.id)
            # Membership comes from the page's own properties, which mirror the
            # Phase 1.5F membership lists verbatim, so the index stays correct
            # even if a relationship was dropped by a cap.
            self.controls_by_page[entity.id] = list(props.get("control_ids") or [])
            self.forms_by_page[entity.id] = list(props.get("form_ids") or [])
            self.apis_by_page[entity.id] = list(props.get("api_endpoint_ids") or [])

        elif etype == ENTITY_REQUIREMENT:
            self.requirements_by_id[entity.id] = entity.id
            if entity.source_entity_id:
                self.requirements_by_id.setdefault(entity.source_entity_id, entity.id)

        elif etype == ENTITY_MODULE:
            self.modules_by_id[entity.id] = entity.id
            if entity.source_entity_id:
                self.modules_by_id.setdefault(entity.source_entity_id, entity.id)

        elif etype == ENTITY_USER_FLOW:
            self.flows_by_id[entity.id] = entity.id
            if entity.source_entity_id:
                self.flows_by_id.setdefault(entity.source_entity_id, entity.id)

    # -- accessors ----------------------------------------------------------

    def entity(self, entity_id: str) -> Optional[KnowledgeEntity]:
        return self.entities_by_id.get(entity_id)

    def resolve(self, entity_id: str) -> Optional[str]:
        """
        Resolve any identifier the caller may hold — a knowledge id, a Phase 1.5F
        id, or a requirement id — to a canonical knowledge entity id.
        """
        if not entity_id:
            return None
        if entity_id in self.entities_by_id:
            return entity_id
        for table in (self.entities_by_source_id, self.requirements_by_id,
                      self.modules_by_id, self.flows_by_id):
            resolved = table.get(entity_id)
            if resolved:
                return resolved
        return None

    def of_type(self, entity_type: str) -> List[KnowledgeEntity]:
        return [
            self.entities_by_id[eid]
            for eid in self.entities_by_type.get(entity_type, [])
            if eid in self.entities_by_id
        ]

    def outgoing(self, entity_id: str) -> List[KnowledgeRelationship]:
        return [
            self.relationships_by_id[rid]
            for rid in self.relationships_by_source.get(entity_id, [])
            if rid in self.relationships_by_id
        ]

    def incoming(self, entity_id: str) -> List[KnowledgeRelationship]:
        return [
            self.relationships_by_id[rid]
            for rid in self.relationships_by_target.get(entity_id, [])
            if rid in self.relationships_by_id
        ]

    def of_relationship_type(self, relationship: str) -> List[KnowledgeRelationship]:
        return [
            self.relationships_by_id[rid]
            for rid in self.relationships_by_type.get(relationship, [])
            if rid in self.relationships_by_id
        ]

    def application_entity(self) -> Optional[KnowledgeEntity]:
        entities = self.of_type(ENTITY_APPLICATION)
        return entities[0] if entities else None

    def counts(self) -> Dict[str, int]:
        return {etype: len(ids) for etype, ids in sorted(self.entities_by_type.items())}

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-safe form (§24). Keys are sorted so that two builds of the same
        model produce byte-identical index output (§52).
        """
        def sorted_map(mapping: Dict[str, Any]) -> Dict[str, Any]:
            return {key: mapping[key] for key in sorted(mapping)}

        return {
            # Position maps, not entity payloads — see the module docstring.
            "entities_by_id": sorted_map(self.entity_positions),
            "entities_by_type": {
                key: list(self.entities_by_type[key]) for key in sorted(self.entities_by_type)
            },
            "entities_by_name": {
                key: list(self.entities_by_name[key]) for key in sorted(self.entities_by_name)
            },
            "entities_by_source_id": sorted_map(self.entities_by_source_id),
            "pages_by_url": sorted_map(self.pages_by_url),
            "controls_by_page": {
                key: list(self.controls_by_page[key]) for key in sorted(self.controls_by_page)
            },
            "forms_by_page": {
                key: list(self.forms_by_page[key]) for key in sorted(self.forms_by_page)
            },
            "apis_by_page": {
                key: list(self.apis_by_page[key]) for key in sorted(self.apis_by_page)
            },
            "requirements_by_id": sorted_map(self.requirements_by_id),
            "modules_by_id": sorted_map(self.modules_by_id),
            "flows_by_id": sorted_map(self.flows_by_id),
            "relationships_by_id": sorted_map(self.relationship_positions),
            "relationships_by_source": {
                key: list(self.relationships_by_source[key])
                for key in sorted(self.relationships_by_source)
            },
            "relationships_by_target": {
                key: list(self.relationships_by_target[key])
                for key in sorted(self.relationships_by_target)
            },
            "relationships_by_type": {
                key: list(self.relationships_by_type[key])
                for key in sorted(self.relationships_by_type)
            },
        }


#: Entity types that carry a page-scoped membership index. Exposed so the
#: validators can check index/graph agreement without re-deriving the list.
PAGE_SCOPED_INDEXES = {
    "controls_by_page": ENTITY_CONTROL,
    "forms_by_page": ENTITY_FORM,
    "apis_by_page": ENTITY_API_ENDPOINT,
}

#: Entity types that must appear at most once in a well-formed model.
SINGLETON_ENTITY_TYPES = (ENTITY_APPLICATION,)

#: Entity types that are never derived from a Phase 1.5F entity and therefore
#: legitimately carry ``source_entity_id is None``.
SYNTHESIZED_ENTITY_TYPES = (
    ENTITY_APPLICATION,
    ENTITY_TECHNOLOGY,
    ENTITY_REPOSITORY_FILE,
    "repository_symbol",
)

__all__ = [
    "KnowledgeIndex",
    "PAGE_SCOPED_INDEXES",
    "SINGLETON_ENTITY_TYPES",
    "SYNTHESIZED_ENTITY_TYPES",
]
