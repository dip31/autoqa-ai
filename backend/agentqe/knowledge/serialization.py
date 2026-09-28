"""
Phase 1.5G — Knowledge model serialization (§37).

``to_dict`` / ``from_dict`` / ``to_json`` / ``from_json`` plus
``deterministic_fingerprint``, which the mandatory §52 rebuild test uses.

What is never serialized
------------------------
Playwright objects, browser handles, sockets, live class instances that cannot
be reconstructed, raw image bytes, raw DOM HTML, and sensitive network data.
The knowledge model only ever holds strings, numbers, booleans, ``None``, lists
and dicts — so ``json.dumps`` on a well-formed model cannot fail, and the
validator's ``privacy_and_serializability`` check proves it on every build.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from agentqe.knowledge.interfaces import KnowledgeModelError
from agentqe.knowledge.schemas import (
    KNOWLEDGE_MODEL_VERSION,
    VOLATILE_PROVENANCE_FIELDS,
    ApplicationKnowledgeModel,
)


def to_dict(model: ApplicationKnowledgeModel) -> Dict[str, Any]:
    """JSON-safe dict form of a knowledge model."""
    if not isinstance(model, ApplicationKnowledgeModel):
        raise KnowledgeModelError(
            f"to_dict expects an ApplicationKnowledgeModel, got {type(model).__name__}.",
            error_code="KNOWLEDGE_SERIALIZATION_TYPE",
        )
    return model.to_dict()


def from_dict(data: Any) -> ApplicationKnowledgeModel:
    """
    Rebuild a knowledge model from its dict form.

    Round-trip guarantee: ``from_dict(to_dict(m))`` produces a model whose
    ``to_dict()`` equals ``to_dict(m)``. Unknown top-level keys are preserved
    under ``metadata['unrecognized_keys']`` rather than dropped, so a newer
    producer's output survives an older reader.
    """
    if not isinstance(data, dict):
        raise KnowledgeModelError(
            f"from_dict expects a mapping, got {type(data).__name__}.",
            error_code="KNOWLEDGE_DESERIALIZATION_TYPE",
        )
    version = data.get("model_version")
    if version and version != KNOWLEDGE_MODEL_VERSION:
        # Forward-compatible read: the shape is additive within 1.x, so parse it
        # and let the validator flag the mismatch rather than refusing outright.
        pass
    return ApplicationKnowledgeModel.from_dict(data)


def to_json(model: ApplicationKnowledgeModel, indent: Optional[int] = None) -> str:
    """Serialize to a JSON string with sorted keys, so output is byte-stable."""
    return json.dumps(to_dict(model), indent=indent, sort_keys=True, ensure_ascii=False)


def from_json(payload: str) -> ApplicationKnowledgeModel:
    """Parse a JSON string produced by ``to_json``."""
    if not isinstance(payload, str):
        raise KnowledgeModelError(
            f"from_json expects a string, got {type(payload).__name__}.",
            error_code="KNOWLEDGE_DESERIALIZATION_TYPE",
        )
    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise KnowledgeModelError(
            f"Knowledge model JSON could not be parsed: {exc}",
            error_code="KNOWLEDGE_DESERIALIZATION_PARSE",
        ) from exc
    return from_dict(data)


# ---------------------------------------------------------------------------
# Determinism support (§52)
# ---------------------------------------------------------------------------

def strip_volatile(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of ``data`` with wall-clock-dependent provenance removed.

    ``generated_at`` and ``duration_ms`` legitimately differ between two builds
    of the same input, so they are excluded before any equality or hash
    comparison. Everything else — every entity id, relationship id, index and
    summary — must match exactly.
    """
    if not isinstance(data, dict):
        return data
    stripped = dict(data)
    provenance = stripped.get("provenance")
    if isinstance(provenance, dict):
        provenance = dict(provenance)
        for field_name in VOLATILE_PROVENANCE_FIELDS:
            provenance.pop(field_name, None)
        stripped["provenance"] = provenance
    return stripped


def deterministic_fingerprint(model: ApplicationKnowledgeModel) -> str:
    """
    A sha256 over the model's serialized form with volatile fields removed.

    Two builds from the same ``UnifiedApplicationModel`` must produce the same
    fingerprint. This is the single assertion the mandatory rebuild test turns
    on (§52).
    """
    payload = strip_volatile(to_dict(model))
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def structural_fingerprint(model: ApplicationKnowledgeModel) -> Dict[str, Any]:
    """
    A human-readable companion to ``deterministic_fingerprint``.

    When two builds disagree, comparing these dicts shows *where* — which id
    list, which count — instead of just reporting two different hashes.
    """
    return {
        "model_version": model.model_version,
        "entity_ids": [e.id for e in (model.entities or [])],
        "relationship_ids": [r.id for r in (model.relationships or [])],
        "entity_count": len(model.entities or []),
        "relationship_count": len(model.relationships or []),
        "index_keys": sorted((model.indexes or {}).keys()),
        "index_sizes": {
            key: len(value) if isinstance(value, (dict, list)) else None
            for key, value in sorted((model.indexes or {}).items())
        },
        "summary_keys": sorted((model.summaries or {}).keys()),
        "application_summary": (model.summaries or {}).get("application_summary", {}),
    }


__all__ = [
    "to_dict",
    "from_dict",
    "to_json",
    "from_json",
    "strip_volatile",
    "deterministic_fingerprint",
    "structural_fingerprint",
]
