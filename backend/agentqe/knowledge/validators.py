"""
Phase 1.5G — Knowledge model validators (§36).

Twenty structural, semantic and safety checks over an
``ApplicationKnowledgeModel``. The validator is strictly **read-only**: it
reports problems, it never repairs them and it never silently removes an
invalid entity or relationship (§36). A caller decides what to do with the
report.

Return shape::

    {
      "valid": bool,
      "error_count": int,
      "warning_count": int,
      "errors": [ {"check": str, "message": str, "entity_id": str|None}, ... ],
      "warnings": [ ... ],
      "checks_run": [ str, ... ],
      "counts": { ... }
    }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from agentqe.knowledge.index import (
    KnowledgeIndex,
    SINGLETON_ENTITY_TYPES,
    SYNTHESIZED_ENTITY_TYPES,
)
from agentqe.knowledge.schemas import (
    ENTITY_ID_PREFIXES,
    ENTITY_TYPES,
    INFERRED,
    KNOWLEDGE_MODEL_VERSION,
    OBSERVATION_STATUSES,
    OBSERVED,
    RELATIONSHIP_TYPES,
    UNKNOWN,
    ApplicationKnowledgeModel,
    KnowledgeEntity,
    KnowledgeRelationship,
)

#: Cap on reported issues so a pathological model cannot produce a megabyte of
#: JSON. Counts remain exact; only the listings are truncated.
MAX_REPORTED = 200

#: Property/field names that must never appear in a knowledge model (§50).
#: Mirrors the Phase 1.5F fusion validator so the two layers agree.
FORBIDDEN_KEY_PATTERN = re.compile(
    r"(password|passwd|pwd|secret|token|authorization|auth_header|cookie"
    r"|api[_-]?key|apikey|credential|bearer|session[_-]?id|csrf|private[_-]?key"
    r"|headers|post_data_raw|request_body|response_body)",
    re.IGNORECASE,
)

#: Screenshots must stay references, never inline bytes (§50).
EMBEDDED_IMAGE_PATTERN = re.compile(r"(data:image/|;base64,)")

#: A credential smuggled through a URL query string.
URL_CREDENTIAL_PATTERN = re.compile(
    r"[?&](password|passwd|token|access[_-]?token|id[_-]?token|refresh[_-]?token"
    r"|api[_-]?key|apikey|secret|session[_-]?id|sessionid|auth)=[^&\s]{4,}",
    re.IGNORECASE,
)

#: A bare bearer credential embedded in a string value.
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}")

#: Any single string longer than this is almost certainly a raw payload
#: (DOM fragment, response body, encoded image) rather than a reference.
MAX_STRING_VALUE_LENGTH = 4000

#: Containers whose *dict keys are data*, not schema field names — entity ids,
#: relationship ids, URLs, entity-type names.
#:
#: The distinction matters. ``FORBIDDEN_KEY_PATTERN`` exists to catch a schema
#: field called ``authorization`` or ``cookie``, which would mean a credential
#: had been copied into the model. It must NOT fire on ``control:password``,
#: because a login form genuinely contains a field named "password" and the
#: knowledge model has to be able to say so — that is exactly the knowledge a
#: test generator needs. What is forbidden is the *value* a user would type into
#: that field, and the knowledge model never captures typed values.
#:
#: Data keys are still checked, but against the value-level patterns: a URL used
#: as an index key could itself smuggle ``?access_token=...``.
_DATA_KEYED_CONTAINERS = re.compile(
    r"^("
    r"indexes\.[a-z_]+"
    r"|summaries\.(module|page|flow|requirement)_summaries"
    r"|summaries\.application_summary\.(entities_by_type|entities_by_status"
    r"|relationships_by_type|relationships_by_status)"
    r"|counts\.[a-z_]+"
    r"|(application|entities\[\d+\])\.properties\.technology_stack"
    r")$"
)

CHECKS = (
    "model_version",
    "entity_ids_unique",
    "entity_id_format",
    "entity_types_valid",
    "entity_required_fields",
    "entity_observation_status",
    "entity_confidence_range",
    "entity_inference_reason",
    "entity_source_traceability",
    "relationship_ids_unique",
    "relationship_endpoints_resolve",
    "relationship_types_valid",
    "relationship_no_self_loops",
    "relationship_no_duplicates",
    "relationship_status_and_confidence",
    "relationship_provenance",
    "index_consistency",
    "summary_consistency",
    "provenance_complete",
    "privacy_and_serializability",
)


class _Report:
    """Accumulates errors and warnings without ever mutating the model."""

    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.error_count = 0
        self.warning_count = 0

    def error(self, check: str, message: str, entity_id: Optional[str] = None) -> None:
        self.error_count += 1
        if len(self.errors) < MAX_REPORTED:
            self.errors.append({"check": check, "message": message, "entity_id": entity_id})

    def warn(self, check: str, message: str, entity_id: Optional[str] = None) -> None:
        self.warning_count += 1
        if len(self.warnings) < MAX_REPORTED:
            self.warnings.append({"check": check, "message": message, "entity_id": entity_id})


def validate_knowledge_model(model: Any) -> Dict[str, Any]:
    """Run all twenty checks and return a structured report."""
    report = _Report()

    if not isinstance(model, ApplicationKnowledgeModel):
        report.error(
            "model_version",
            f"Expected an ApplicationKnowledgeModel, got {type(model).__name__}.",
        )
        return _finalize(report, {}, [])

    entities: List[KnowledgeEntity] = [
        e for e in (model.entities or []) if isinstance(e, KnowledgeEntity)
    ]
    relationships: List[KnowledgeRelationship] = [
        r for r in (model.relationships or []) if isinstance(r, KnowledgeRelationship)
    ]
    if len(entities) != len(model.entities or []):
        report.error(
            "entity_required_fields",
            "The entities list contains objects that are not KnowledgeEntity instances.",
        )
    if len(relationships) != len(model.relationships or []):
        report.error(
            "relationship_provenance",
            "The relationships list contains objects that are not KnowledgeRelationship "
            "instances.",
        )

    entity_ids: Set[str] = set()

    # 1 -----------------------------------------------------------------
    _check_model_version(model, report)
    # 2-9 ---------------------------------------------------------------
    _check_entities(entities, entity_ids, report)
    # 10-16 --------------------------------------------------------------
    _check_relationships(relationships, entity_ids, report)
    # 17 -----------------------------------------------------------------
    _check_indexes(model, entities, relationships, report)
    # 18 -----------------------------------------------------------------
    _check_summaries(model, entities, relationships, report)
    # 19 -----------------------------------------------------------------
    _check_provenance(model, report)
    # 20 -----------------------------------------------------------------
    _check_privacy_and_serializability(model, report)

    counts = {
        "entities": len(entities),
        "relationships": len(relationships),
        "entities_by_type": _counter([e.entity_type for e in entities]),
        "entities_by_status": _counter([e.status for e in entities]),
        "relationships_by_type": _counter([r.relationship for r in relationships]),
        "relationships_by_status": _counter([r.status for r in relationships]),
    }
    return _finalize(report, counts, list(CHECKS))


# ---------------------------------------------------------------------------
# Check 1 — model version (§35)
# ---------------------------------------------------------------------------

def _check_model_version(model: ApplicationKnowledgeModel, report: _Report) -> None:
    if not model.model_version:
        report.error("model_version", "model_version is missing.")
    elif model.model_version != KNOWLEDGE_MODEL_VERSION:
        report.warn(
            "model_version",
            f"model_version is '{model.model_version}' but this build of AgentQE writes "
            f"'{KNOWLEDGE_MODEL_VERSION}'. The model may have been produced by a different "
            "version.",
        )


# ---------------------------------------------------------------------------
# Checks 2-9 — entities
# ---------------------------------------------------------------------------

def _check_entities(
    entities: List[KnowledgeEntity], entity_ids: Set[str], report: _Report
) -> None:
    type_counts: Dict[str, int] = {}

    for entity in entities:
        # 2 — unique ids
        if not entity.id:
            report.error("entity_ids_unique", "An entity has an empty id.")
            continue
        if entity.id in entity_ids:
            report.error("entity_ids_unique", f"Duplicate entity id '{entity.id}'.", entity.id)
        entity_ids.add(entity.id)

        # 4 — known type (checked before the id-format check, which needs it)
        if entity.entity_type not in ENTITY_TYPES:
            report.error(
                "entity_types_valid",
                f"Entity type '{entity.entity_type}' is not in the controlled vocabulary.",
                entity.id,
            )
        else:
            type_counts[entity.entity_type] = type_counts.get(entity.entity_type, 0) + 1

            # 3 — id format
            prefix = ENTITY_ID_PREFIXES.get(entity.entity_type)
            if prefix and not entity.id.startswith(f"{prefix}:"):
                report.error(
                    "entity_id_format",
                    f"Entity id '{entity.id}' does not start with the '{prefix}:' prefix "
                    f"required for type '{entity.entity_type}'.",
                    entity.id,
                )
            if entity.id != entity.id.strip() or " " in entity.id:
                report.error(
                    "entity_id_format",
                    f"Entity id '{entity.id}' contains whitespace.",
                    entity.id,
                )

        # 5 — required fields
        if not (entity.display_name or entity.name):
            report.error(
                "entity_required_fields",
                f"Entity '{entity.id}' has neither a name nor a display_name.",
                entity.id,
            )
        if not entity.canonical_name:
            report.warn(
                "entity_required_fields",
                f"Entity '{entity.id}' has no canonical_name, so normalized lookup will miss it.",
                entity.id,
            )
        if not isinstance(entity.properties, dict):
            report.error(
                "entity_required_fields",
                f"Entity '{entity.id}' has non-dict properties.",
                entity.id,
            )

        # 6 — observation status
        if entity.status not in OBSERVATION_STATUSES:
            report.error(
                "entity_observation_status",
                f"Entity '{entity.id}' has invalid status '{entity.status}'.",
                entity.id,
            )

        # 7 — confidence range
        if entity.confidence is not None:
            if not isinstance(entity.confidence, (int, float)) or isinstance(entity.confidence, bool):
                report.error(
                    "entity_confidence_range",
                    f"Entity '{entity.id}' has non-numeric confidence "
                    f"{entity.confidence!r}.",
                    entity.id,
                )
            elif not (0.0 <= float(entity.confidence) <= 1.0):
                report.error(
                    "entity_confidence_range",
                    f"Entity '{entity.id}' has confidence {entity.confidence} outside [0, 1].",
                    entity.id,
                )
            if entity.status == OBSERVED and entity.confidence_basis is None:
                report.warn(
                    "entity_confidence_range",
                    f"Entity '{entity.id}' carries a confidence value with no "
                    "confidence_basis explaining where it came from.",
                    entity.id,
                )

        # 8 — inferred entities must explain themselves (§32)
        if entity.status == INFERRED and not entity.inference_reason:
            report.error(
                "entity_inference_reason",
                f"Entity '{entity.id}' is inferred but has no inference_reason.",
                entity.id,
            )
        if entity.status == OBSERVED and entity.inference_reason:
            report.warn(
                "entity_inference_reason",
                f"Entity '{entity.id}' is marked observed but carries an inference_reason, "
                "which is contradictory.",
                entity.id,
            )

        # 9 — traceability (§23)
        if entity.source_entity_id is None and entity.entity_type not in SYNTHESIZED_ENTITY_TYPES:
            report.error(
                "entity_source_traceability",
                f"Entity '{entity.id}' has no source_entity_id and its type "
                f"'{entity.entity_type}' is not one that the builder synthesizes.",
                entity.id,
            )
        if not entity.evidence_refs:
            report.warn(
                "entity_source_traceability",
                f"Entity '{entity.id}' has no evidence_refs, so it cannot be traced back to "
                "raw evidence.",
                entity.id,
            )

    for singleton in SINGLETON_ENTITY_TYPES:
        count = type_counts.get(singleton, 0)
        if count > 1:
            report.error(
                "entity_types_valid",
                f"Found {count} '{singleton}' entities; exactly one is expected.",
            )
        elif count == 0 and entities:
            report.warn(
                "entity_types_valid",
                f"No '{singleton}' entity was produced, so the graph has no root.",
            )


# ---------------------------------------------------------------------------
# Checks 10-16 — relationships
# ---------------------------------------------------------------------------

def _check_relationships(
    relationships: List[KnowledgeRelationship], entity_ids: Set[str], report: _Report
) -> None:
    seen_ids: Set[str] = set()
    seen_triples: Set[Tuple[str, str, str]] = set()

    for rel in relationships:
        # 10 — unique ids
        if not rel.id:
            report.error("relationship_ids_unique", "A relationship has an empty id.")
            continue
        if rel.id in seen_ids:
            report.error("relationship_ids_unique", f"Duplicate relationship id '{rel.id}'.", rel.id)
        seen_ids.add(rel.id)

        # 11 — endpoints resolve
        if rel.source_id not in entity_ids:
            report.error(
                "relationship_endpoints_resolve",
                f"Relationship '{rel.id}' has source '{rel.source_id}' which is not an entity "
                "in this model.",
                rel.id,
            )
        if rel.target_id not in entity_ids:
            report.error(
                "relationship_endpoints_resolve",
                f"Relationship '{rel.id}' has target '{rel.target_id}' which is not an entity "
                "in this model.",
                rel.id,
            )

        # 12 — known type
        if rel.relationship not in RELATIONSHIP_TYPES:
            report.error(
                "relationship_types_valid",
                f"Relationship '{rel.id}' uses type '{rel.relationship}', which is not in the "
                "controlled vocabulary.",
                rel.id,
            )

        # 13 — no self loops
        if rel.source_id and rel.source_id == rel.target_id:
            report.error(
                "relationship_no_self_loops",
                f"Relationship '{rel.id}' points an entity at itself.",
                rel.id,
            )

        # 14 — no duplicate triples
        triple = (rel.source_id, rel.relationship, rel.target_id)
        if triple in seen_triples:
            report.error(
                "relationship_no_duplicates",
                f"Duplicate relationship {rel.source_id} --{rel.relationship}--> "
                f"{rel.target_id}.",
                rel.id,
            )
        seen_triples.add(triple)

        # 15 — status and confidence honesty (§32, §33)
        if rel.status not in OBSERVATION_STATUSES:
            report.error(
                "relationship_status_and_confidence",
                f"Relationship '{rel.id}' has invalid status '{rel.status}'.",
                rel.id,
            )
        if rel.confidence is not None:
            if not isinstance(rel.confidence, (int, float)) or isinstance(rel.confidence, bool):
                report.error(
                    "relationship_status_and_confidence",
                    f"Relationship '{rel.id}' has non-numeric confidence {rel.confidence!r}.",
                    rel.id,
                )
            elif not (0.0 <= float(rel.confidence) <= 1.0):
                report.error(
                    "relationship_status_and_confidence",
                    f"Relationship '{rel.id}' has confidence {rel.confidence} outside [0, 1].",
                    rel.id,
                )
        if rel.status == INFERRED and not rel.inference_reason:
            report.error(
                "relationship_status_and_confidence",
                f"Relationship '{rel.id}' is inferred but has no inference_reason.",
                rel.id,
            )

        # 16 — every edge explains why it exists (§23)
        if not rel.source_relationship_id and not rel.derivation:
            report.error(
                "relationship_provenance",
                f"Relationship '{rel.id}' records neither a source_relationship_id nor a "
                "derivation, so it cannot answer why it exists.",
                rel.id,
            )


# ---------------------------------------------------------------------------
# Check 17 — indexes agree with the graph (§24)
# ---------------------------------------------------------------------------

def _check_indexes(
    model: ApplicationKnowledgeModel,
    entities: List[KnowledgeEntity],
    relationships: List[KnowledgeRelationship],
    report: _Report,
) -> None:
    indexes = model.indexes or {}
    if not indexes:
        report.warn("index_consistency", "The model carries no indexes.")
        return

    entity_ids = {e.id for e in entities}
    relationship_ids = {r.id for r in relationships}

    by_id = indexes.get("entities_by_id") or {}
    if len(by_id) != len(entity_ids):
        report.error(
            "index_consistency",
            f"entities_by_id holds {len(by_id)} keys but the model has {len(entity_ids)} "
            "entities.",
        )
    missing = [eid for eid in by_id if eid not in entity_ids]
    if missing:
        report.error(
            "index_consistency",
            f"entities_by_id references {len(missing)} id(s) that are not in the entities list, "
            f"e.g. {missing[0]}.",
        )

    indexed_by_type = indexes.get("entities_by_type") or {}
    total_typed = sum(len(v) for v in indexed_by_type.values())
    if total_typed != len(entity_ids):
        report.error(
            "index_consistency",
            f"entities_by_type covers {total_typed} entities but the model has "
            f"{len(entity_ids)}.",
        )

    for index_name in ("controls_by_page", "forms_by_page", "apis_by_page"):
        for page_id, member_ids in (indexes.get(index_name) or {}).items():
            if page_id not in entity_ids:
                report.error(
                    "index_consistency",
                    f"{index_name} is keyed by '{page_id}', which is not an entity.",
                    page_id,
                )
            for member_id in member_ids:
                if member_id not in entity_ids:
                    report.error(
                        "index_consistency",
                        f"{index_name}['{page_id}'] references unknown entity '{member_id}'.",
                        page_id,
                    )

    for index_name in ("relationships_by_source", "relationships_by_target"):
        for key, rel_ids in (indexes.get(index_name) or {}).items():
            if key not in entity_ids:
                report.error(
                    "index_consistency",
                    f"{index_name} is keyed by '{key}', which is not an entity.",
                    key,
                )
            for rel_id in rel_ids:
                if rel_id not in relationship_ids:
                    report.error(
                        "index_consistency",
                        f"{index_name}['{key}'] references unknown relationship '{rel_id}'.",
                        key,
                    )

    for page_url, page_id in (indexes.get("pages_by_url") or {}).items():
        if page_id not in entity_ids:
            report.error(
                "index_consistency",
                f"pages_by_url['{page_url}'] points at unknown entity '{page_id}'.",
            )

    # Rebuild from scratch and compare: the index must be a pure function of
    # the entity/relationship lists (§24).
    rebuilt = KnowledgeIndex.build(model).to_dict()
    for key in sorted(set(rebuilt) | set(indexes)):
        if rebuilt.get(key) != indexes.get(key):
            report.error(
                "index_consistency",
                f"Index '{key}' does not match a fresh rebuild from the entity and "
                "relationship lists.",
            )


# ---------------------------------------------------------------------------
# Check 18 — summaries agree with the data (§29)
# ---------------------------------------------------------------------------

def _check_summaries(
    model: ApplicationKnowledgeModel,
    entities: List[KnowledgeEntity],
    relationships: List[KnowledgeRelationship],
    report: _Report,
) -> None:
    summaries = model.summaries or {}
    if not summaries:
        report.warn("summary_consistency", "The model carries no summaries.")
        return

    app_summary = summaries.get("application_summary") or {}
    actual_types = _counter([e.entity_type for e in entities])

    expectations = {
        "page_count": actual_types.get("page", 0),
        "control_count": actual_types.get("control", 0),
        "form_count": actual_types.get("form", 0),
        "api_count": actual_types.get("api_endpoint", 0),
        "flow_count": actual_types.get("user_flow", 0),
        "module_count": actual_types.get("module", 0),
        "requirement_count": actual_types.get("requirement", 0),
        "entity_count": len(entities),
        "relationship_count": len(relationships),
    }
    for key, expected in expectations.items():
        reported = app_summary.get(key)
        if reported is None:
            report.warn("summary_consistency", f"application_summary is missing '{key}'.")
        elif reported != expected:
            report.error(
                "summary_consistency",
                f"application_summary['{key}'] is {reported} but the model contains "
                f"{expected}.",
            )

    for summary_name, entity_type in (
        ("module_summaries", "module"),
        ("page_summaries", "page"),
        ("flow_summaries", "user_flow"),
        ("requirement_summaries", "requirement"),
    ):
        block = summaries.get(summary_name)
        if block is None:
            report.warn("summary_consistency", f"'{summary_name}' is missing.")
            continue
        expected_ids = {e.id for e in entities if e.entity_type == entity_type}
        if set(block.keys()) != expected_ids:
            report.error(
                "summary_consistency",
                f"{summary_name} covers {len(block)} entities but the model has "
                f"{len(expected_ids)} of type '{entity_type}'.",
            )


# ---------------------------------------------------------------------------
# Check 19 — provenance (§34)
# ---------------------------------------------------------------------------

def _check_provenance(model: ApplicationKnowledgeModel, report: _Report) -> None:
    provenance = model.provenance
    if provenance is None:
        report.error("provenance_complete", "The model has no provenance block.")
        return

    for field_name in ("source_model", "knowledge_model_version", "generated_at", "builder"):
        if not getattr(provenance, field_name, None):
            report.error("provenance_complete", f"provenance.{field_name} is missing.")

    if provenance.llm_used:
        report.error(
            "provenance_complete",
            "provenance.llm_used is true. Phase 1.5G must build the knowledge model "
            "deterministically, without an LLM.",
        )
    if not provenance.fusion_version:
        report.warn(
            "provenance_complete",
            "provenance.fusion_version is missing, so the model cannot be traced to the "
            "fusion build that produced it.",
        )


# ---------------------------------------------------------------------------
# Check 20 — privacy and serializability (§37, §50)
# ---------------------------------------------------------------------------

def _check_privacy_and_serializability(model: ApplicationKnowledgeModel, report: _Report) -> None:
    try:
        payload = model.to_dict()
    except Exception as exc:
        report.error(
            "privacy_and_serializability",
            f"The model could not be converted to a dict: {exc}",
        )
        return

    try:
        json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        report.error(
            "privacy_and_serializability",
            f"The model is not JSON-serializable, which means it holds a live object such as "
            f"a Playwright handle: {exc}",
        )

    findings: List[str] = []
    _walk(payload, "", findings, set())
    for finding in findings[:MAX_REPORTED]:
        report.error("privacy_and_serializability", finding)
    if len(findings) > MAX_REPORTED:
        report.error_count += len(findings) - MAX_REPORTED


def _walk(
    node: Any,
    path: str,
    findings: List[str],
    seen: Set[int],
    keys_are_data: bool = False,
) -> None:
    if isinstance(node, dict):
        if id(node) in seen:
            return
        seen.add(id(node))
        for key, value in node.items():
            key_str = str(key)
            child_path = f"{path}.{key_str}" if path else key_str
            if keys_are_data:
                # An entity id, URL or type name. Check it the way a value is
                # checked — see _DATA_KEYED_CONTAINERS for why.
                _check_string(key_str, f"{path}[key]", findings)
            elif FORBIDDEN_KEY_PATTERN.search(key_str):
                findings.append(
                    f"Field '{child_path}' has a name that suggests credential or raw header "
                    "data, which must never enter the knowledge model."
                )
            _walk(
                value,
                child_path,
                findings,
                seen,
                keys_are_data=_DATA_KEYED_CONTAINERS.search(child_path) is not None,
            )
    elif isinstance(node, (list, tuple)):
        if id(node) in seen:
            return
        seen.add(id(node))
        for position, value in enumerate(node):
            _walk(value, f"{path}[{position}]", findings, seen)
    elif isinstance(node, str):
        _check_string(node, path, findings)


def _check_string(value: str, path: str, findings: List[str]) -> None:
    """
    Value-level safety checks (§37, §50).

    These run on every string in the payload with no exemptions. The two
    credential patterns require literal ``?key=value`` syntax or a ``Bearer``
    prefix followed by 16+ token characters, so builder-written prose such as
    "no authorization header was captured" cannot match them — there is no need
    to whitelist explanatory fields, and whitelisting them would leave a place
    for a real credential to hide.
    """
    if EMBEDDED_IMAGE_PATTERN.search(value):
        findings.append(
            f"Field '{path}' contains inline image data. Screenshots must be referenced by "
            "path, never embedded."
        )
    if len(value) > MAX_STRING_VALUE_LENGTH:
        findings.append(
            f"Field '{path}' holds a {len(value)}-character string, which looks like a raw "
            f"payload rather than a reference (limit {MAX_STRING_VALUE_LENGTH})."
        )
    if URL_CREDENTIAL_PATTERN.search(value):
        findings.append(
            f"Field '{path}' contains a URL with a credential-bearing query parameter."
        )
    if BEARER_PATTERN.search(value):
        findings.append(f"Field '{path}' contains a bearer credential.")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _counter(values: List[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return {k: counts[k] for k in sorted(counts)}


def _finalize(report: _Report, counts: Dict[str, Any], checks_run: List[str]) -> Dict[str, Any]:
    return {
        "valid": report.error_count == 0,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "errors": report.errors,
        "warnings": report.warnings,
        "checks_run": checks_run,
        "counts": counts,
        "truncated": report.error_count > len(report.errors)
        or report.warning_count > len(report.warnings),
    }


__all__ = [
    "validate_knowledge_model",
    "CHECKS",
    "MAX_REPORTED",
    "FORBIDDEN_KEY_PATTERN",
    "EMBEDDED_IMAGE_PATTERN",
    "URL_CREDENTIAL_PATTERN",
    "BEARER_PATTERN",
    "MAX_STRING_VALUE_LENGTH",
]
