"""
Phase 1.5G — In-memory knowledge graph and deterministic summaries.

Two things live here:

``KnowledgeGraph``
    A thin adjacency wrapper over the entity/relationship lists. It is a plain
    dict-of-lists on purpose: Phase 1.5G explicitly forbids Neo4j, ArangoDB,
    Neptune, or NetworkX-as-a-database (§28). Keeping traversal behind this one
    class means a graph backend could be substituted later without touching the
    query layer.

``build_summaries``
    Deterministic roll-ups computed by counting real model data. No LLM, no
    prose generation, no heuristics (§29).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from agentqe.knowledge.index import KnowledgeIndex
from agentqe.knowledge.schemas import (
    ENTITY_API_ENDPOINT,
    ENTITY_CONTROL,
    ENTITY_FORM,
    ENTITY_MODULE,
    ENTITY_PAGE,
    ENTITY_REPOSITORY_FILE,
    ENTITY_REPOSITORY_SYMBOL,
    ENTITY_REQUIREMENT,
    ENTITY_TECHNOLOGY,
    ENTITY_USER_FLOW,
    INFERRED,
    OBSERVED,
    SATISFIES,
    UNKNOWN,
    ApplicationKnowledgeModel,
    KnowledgeEntity,
    KnowledgeRelationship,
)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@dataclass
class GraphEdge:
    """One directed edge, kept alongside the relationship it came from."""
    relationship_id: str
    source_id: str
    relationship: str
    target_id: str
    direction: str  # "outgoing" | "incoming" — relative to the queried node


class KnowledgeGraph:
    """
    Adjacency view over an ``ApplicationKnowledgeModel``.

    Traversal is bounded and deterministic: neighbours are returned in the order
    the relationships appear in the model, and every traversal takes an explicit
    depth and node budget so no query can walk an entire large graph by accident
    (§26).
    """

    def __init__(self, model: ApplicationKnowledgeModel, index: Optional[KnowledgeIndex] = None):
        self.model = model
        self.index = index or KnowledgeIndex.build(model)

    # -- basic access -------------------------------------------------------

    def node(self, entity_id: str) -> Optional[KnowledgeEntity]:
        return self.index.entities_by_id.get(entity_id)

    def has_node(self, entity_id: str) -> bool:
        return entity_id in self.index.entities_by_id

    def edges_of(self, entity_id: str) -> List[GraphEdge]:
        """All edges touching ``entity_id``, outgoing first then incoming."""
        edges: List[GraphEdge] = []
        for rel in self.index.outgoing(entity_id):
            edges.append(GraphEdge(rel.id, rel.source_id, rel.relationship, rel.target_id, "outgoing"))
        for rel in self.index.incoming(entity_id):
            edges.append(GraphEdge(rel.id, rel.source_id, rel.relationship, rel.target_id, "incoming"))
        return edges

    def neighbor_ids(
        self,
        entity_id: str,
        relationship_types: Optional[Iterable[str]] = None,
        direction: str = "both",
    ) -> List[str]:
        """Neighbour ids in model order, de-duplicated."""
        wanted = set(relationship_types) if relationship_types else None
        out: List[str] = []
        for edge in self.edges_of(entity_id):
            if direction != "both" and edge.direction != direction:
                continue
            if wanted is not None and edge.relationship not in wanted:
                continue
            other = edge.target_id if edge.direction == "outgoing" else edge.source_id
            if other != entity_id and other not in out:
                out.append(other)
        return out

    def degree(self, entity_id: str) -> int:
        return (
            len(self.index.relationships_by_source.get(entity_id, []))
            + len(self.index.relationships_by_target.get(entity_id, []))
        )

    # -- bounded traversal --------------------------------------------------

    def subgraph(
        self,
        entity_id: str,
        depth: int = 1,
        max_nodes: int = 200,
        relationship_types: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """
        Breadth-first neighbourhood around ``entity_id``.

        Bounded by both ``depth`` and ``max_nodes`` so a UI graph view can never
        request the whole model (§26, §44).
        """
        if not self.has_node(entity_id):
            return {"root_id": entity_id, "nodes": [], "edges": [], "truncated": False, "depth": depth}

        wanted = set(relationship_types) if relationship_types else None
        visited: Set[str] = {entity_id}
        frontier: List[str] = [entity_id]
        order: List[str] = [entity_id]
        truncated = False

        for _ in range(max(0, depth)):
            next_frontier: List[str] = []
            for node_id in frontier:
                for neighbor in self.neighbor_ids(node_id, wanted):
                    if neighbor in visited:
                        continue
                    if len(order) >= max_nodes:
                        truncated = True
                        break
                    visited.add(neighbor)
                    order.append(neighbor)
                    next_frontier.append(neighbor)
                if truncated:
                    break
            if truncated or not next_frontier:
                break
            frontier = next_frontier

        edge_ids: List[str] = []
        seen_edges: Set[str] = set()
        for node_id in order:
            for edge in self.edges_of(node_id):
                if edge.relationship_id in seen_edges:
                    continue
                if wanted is not None and edge.relationship not in wanted:
                    continue
                if edge.source_id in visited and edge.target_id in visited:
                    seen_edges.add(edge.relationship_id)
                    edge_ids.append(edge.relationship_id)

        return {
            "root_id": entity_id,
            "depth": depth,
            "truncated": truncated,
            "nodes": [self.index.entities_by_id[n].to_dict() for n in order],
            "edges": [self.index.relationships_by_id[e].to_dict() for e in edge_ids],
        }


# ---------------------------------------------------------------------------
# Summaries (§29)
# ---------------------------------------------------------------------------

def _status_counts(items: Iterable[Any]) -> Dict[str, int]:
    counts = {OBSERVED: 0, INFERRED: 0, UNKNOWN: 0}
    for item in items:
        status = getattr(item, "status", None)
        if status in counts:
            counts[status] += 1
        else:
            counts[UNKNOWN] += 1
    return counts


def build_summaries(
    model: ApplicationKnowledgeModel,
    index: Optional[KnowledgeIndex] = None,
) -> Dict[str, Any]:
    """
    Build the deterministic summary block.

    Every value is a count or a copied field. Nothing here is generated prose
    and nothing is estimated — a summary that cannot be computed from the model
    is simply absent (§29).
    """
    index = index or KnowledgeIndex.build(model)
    entities = list(model.entities or [])
    relationships = list(model.relationships or [])

    by_type = index.counts()
    app_entity = index.application_entity()

    relationship_type_counts: Dict[str, int] = {}
    for rel in relationships:
        relationship_type_counts[rel.relationship] = relationship_type_counts.get(rel.relationship, 0) + 1

    control_entities = index.of_type(ENTITY_CONTROL)
    page_entities = index.of_type(ENTITY_PAGE)

    application_summary: Dict[str, Any] = {
        "name": app_entity.display_name if app_entity else None,
        "url": (app_entity.properties.get("url") if app_entity else None),
        "app_type": (app_entity.properties.get("app_type") if app_entity else None),
        "status": app_entity.status if app_entity else UNKNOWN,

        # The counts §29 asks for, by their spec names.
        "page_count": by_type.get(ENTITY_PAGE, 0),
        "control_count": by_type.get(ENTITY_CONTROL, 0),
        "form_count": by_type.get(ENTITY_FORM, 0),
        "api_count": by_type.get(ENTITY_API_ENDPOINT, 0),
        "flow_count": by_type.get(ENTITY_USER_FLOW, 0),
        "module_count": by_type.get(ENTITY_MODULE, 0),
        "requirement_count": by_type.get(ENTITY_REQUIREMENT, 0),
        "technology_count": by_type.get(ENTITY_TECHNOLOGY, 0),
        "repository_file_count": by_type.get(ENTITY_REPOSITORY_FILE, 0),
        "repository_symbol_count": by_type.get(ENTITY_REPOSITORY_SYMBOL, 0),
        "entity_count": len(entities),
        "relationship_count": len(relationships),

        "entities_by_type": by_type,
        "entities_by_status": _status_counts(entities),
        "relationships_by_status": _status_counts(relationships),
        "relationships_by_type": {k: relationship_type_counts[k] for k in sorted(relationship_type_counts)},

        # Coverage signals a planner can act on without re-reading the graph.
        "interactable_control_count": sum(
            1 for c in control_entities if c.properties.get("interactable") is True
        ),
        "pages_with_forms": sum(1 for p in page_entities if p.properties.get("form_ids")),
        "pages_with_apis": sum(1 for p in page_entities if p.properties.get("api_endpoint_ids")),
        "pages_with_repository_matches": sum(1 for p in page_entities if p.repository_refs),
    }

    module_summaries: Dict[str, Any] = {}
    for module in index.of_type(ENTITY_MODULE):
        props = module.properties or {}
        module_summaries[module.id] = {
            "name": module.display_name,
            "status": module.status,
            "source": props.get("source"),
            "page_count": len(props.get("page_ids") or []),
            "control_count": len(props.get("control_ids") or []),
            "form_count": len(props.get("form_ids") or []),
            "api_count": len(props.get("api_endpoint_ids") or []),
            "requirement_count": len(module.requirement_refs or []),
        }

    page_summaries: Dict[str, Any] = {}
    module_ids_by_page: Dict[str, List[str]] = {}
    for module in index.of_type(ENTITY_MODULE):
        for page_id in (module.properties.get("page_ids") or []):
            module_ids_by_page.setdefault(page_id, []).append(module.id)

    for page in page_entities:
        props = page.properties or {}
        page_summaries[page.id] = {
            "name": page.display_name,
            "url": props.get("url"),
            "page_type": props.get("page_type"),
            "page_type_status": props.get("page_type_status"),
            "status": page.status,
            "depth": props.get("depth"),
            "control_count": len(props.get("control_ids") or []),
            "form_count": len(props.get("form_ids") or []),
            "api_count": len(props.get("api_endpoint_ids") or []),
            "module_ids": module_ids_by_page.get(page.id, []),
            "requirement_count": len(page.requirement_refs or []),
            "repository_file_count": len(page.repository_refs or []),
            "has_screenshot": bool(props.get("screenshot_ref")),
        }

    flow_summaries: Dict[str, Any] = {}
    for flow in index.of_type(ENTITY_USER_FLOW):
        props = flow.properties or {}
        steps = props.get("steps") or []
        flow_summaries[flow.id] = {
            "name": flow.display_name,
            "status": flow.status,
            "source": props.get("source"),
            "semantic_role": props.get("semantic_role"),
            "step_count": len(steps),
            "observed_step_count": sum(1 for s in steps if s.get("observation_status") == OBSERVED),
            "inferred_step_count": sum(1 for s in steps if s.get("observation_status") == INFERRED),
            "page_count": len(props.get("page_ids") or []),
            "control_count": len(props.get("control_ids") or []),
            "api_count": len(props.get("api_endpoint_ids") or []),
            "confidence": flow.confidence,
        }

    # Requirement coverage: counted from `satisfies` edges only. A requirement
    # with no such edge is reported as uncovered rather than quietly assumed
    # satisfied (§17).
    requirement_summaries: Dict[str, Any] = {}
    for requirement in index.of_type(ENTITY_REQUIREMENT):
        satisfying = [
            rel for rel in index.incoming(requirement.id) if rel.relationship == SATISFIES
        ]
        requirement_summaries[requirement.id] = {
            "requirement_id": requirement.properties.get("requirement_id"),
            "text": requirement.properties.get("text"),
            "source": requirement.properties.get("source"),
            "status": requirement.status,
            "satisfied_by_count": len(satisfying),
            "satisfied_by": [rel.source_id for rel in satisfying],
            "all_links_inferred": bool(satisfying) and all(
                rel.status != OBSERVED for rel in satisfying
            ),
        }

    return {
        "application_summary": application_summary,
        "module_summaries": module_summaries,
        "page_summaries": page_summaries,
        "flow_summaries": flow_summaries,
        "requirement_summaries": requirement_summaries,
    }


__all__ = [
    "GraphEdge",
    "KnowledgeGraph",
    "build_summaries",
]
