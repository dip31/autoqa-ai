"""
Phase 1.5F — Unified Application Model validators.

The validator is a *reporter*, not a filter: it never mutates or silently drops
anything. It returns a structured report so the agent can attach it to
``fusion_metadata.validation`` and the UI can surface problems honestly.

Checks
------
structure     ids present, unique and well-formed
references    relationship endpoints, form fields, page members, requirement ids
evidence      every entity carries at least one resolvable ``evidence_ref``
vocabulary    control types, relationship types, semantic roles, statuses
geometry      bbox arity / ordering / range
confidence    ``None`` or within [0, 1], and always accompanied by a basis
honesty       ``inferred`` implies an ``inference_reason``; a semantic role is
              never reported as ``observed``; ``observed`` entities do not carry
              a fusion confidence
duplication   no two controls describing the same DOM / visual evidence
privacy       no credential-shaped keys, no embedded image data, no oversized
              payloads copied into the model
"""

import re
from typing import Any, Dict, List, Optional

from agentqe.fusion.schemas import (
    CONTROL_TYPES,
    EVIDENCE_REF_KINDS,
    EVIDENCE_SOURCES,
    INFERRED,
    OBSERVATION_STATUSES,
    OBSERVED,
    RELATIONSHIP_TYPES,
    SEMANTIC_ROLES,
    UNKNOWN,
)

MAX_REPORTED = 200

#: Keys that must never appear anywhere in the unified model (Phase 1.5F §39).
FORBIDDEN_KEY_PATTERN = re.compile(
    r"(password|passwd|pwd|secret|token|authorization|auth_header|cookie|"
    r"api[_-]?key|apikey|credential|bearer|session[_-]?id|csrf|private[_-]?key|"
    r"headers|post_data_raw|request_body|response_body)",
    re.IGNORECASE,
)

#: Values that would indicate image bytes were embedded instead of referenced.
EMBEDDED_IMAGE_PATTERN = re.compile(r"(data:image/|;base64,)", re.IGNORECASE)

MAX_STRING_VALUE_LENGTH = 4000

_ID_PATTERNS = {
    "page": re.compile(r"^page_\d{3,}$"),
    "control": re.compile(r"^control_\d{3,}$"),
    "form": re.compile(r"^form_\d{3,}$"),
    "api_endpoint": re.compile(r"^api_\d{3,}$"),
    "user_flow": re.compile(r"^flow_\d{3,}$"),
    "module": re.compile(r"^module_\d{3,}$"),
    "relationship": re.compile(r"^rel_\d{3,}$"),
}


class _Report:
    """Collects structured findings without ever raising."""

    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.errors_truncated = 0
        self.warnings_truncated = 0

    def error(self, code: str, message: str, entity_type: Optional[str] = None,
              entity_id: Optional[str] = None, field: Optional[str] = None) -> None:
        if len(self.errors) >= MAX_REPORTED:
            self.errors_truncated += 1
            return
        self.errors.append({
            "severity": "error", "code": code, "message": message,
            "entity_type": entity_type, "entity_id": entity_id, "field": field,
        })

    def warn(self, code: str, message: str, entity_type: Optional[str] = None,
             entity_id: Optional[str] = None, field: Optional[str] = None) -> None:
        if len(self.warnings) >= MAX_REPORTED:
            self.warnings_truncated += 1
            return
        self.warnings.append({
            "severity": "warning", "code": code, "message": message,
            "entity_type": entity_type, "entity_id": entity_id, "field": field,
        })


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_unified_model(model: Any) -> Dict[str, Any]:
    """
    Validate a ``UnifiedApplicationModel`` (or its ``to_dict()`` form).

    Returns:
        ``{"valid", "error_count", "warning_count", "errors", "warnings",
        "checks_run", "counts"}``. ``valid`` is ``True`` only when there are no
        errors; warnings never invalidate a model.
    """
    report = _Report()
    data = model.to_dict() if hasattr(model, "to_dict") else (model or {})
    if not isinstance(data, dict):
        report.error("E_MODEL_TYPE", f"Unified model must be a mapping, got {type(data).__name__}.")
        return _finalize(report, {}, [])

    collections = {
        "page": data.get("pages") or [],
        "control": data.get("controls") or [],
        "form": data.get("forms") or [],
        "api_endpoint": data.get("api_endpoints") or [],
        "user_flow": data.get("user_flows") or [],
        "module": data.get("modules") or [],
        "requirement": data.get("requirements") or [],
    }
    relationships = data.get("relationships") or []

    entity_ids = _check_ids(report, collections, relationships)
    page_ids = {p.get("id") for p in collections["page"] if isinstance(p, dict)}
    control_ids = {c.get("id") for c in collections["control"] if isinstance(c, dict)}
    api_ids = {a.get("id") for a in collections["api_endpoint"] if isinstance(a, dict)}
    requirement_ids = {r.get("id") for r in collections["requirement"] if isinstance(r, dict)}

    _check_common_entity_rules(report, collections, page_ids, requirement_ids)
    _check_pages(report, collections["page"], control_ids, api_ids,
                 {f.get("id") for f in collections["form"] if isinstance(f, dict)})
    _check_controls(report, collections["control"], page_ids,
                    {f.get("id") for f in collections["form"] if isinstance(f, dict)})
    _check_forms(report, collections["form"], page_ids, control_ids, api_ids)
    _check_api_endpoints(report, collections["api_endpoint"], page_ids)
    _check_user_flows(report, collections["user_flow"], page_ids, control_ids,
                      api_ids, requirement_ids)
    _check_modules(report, collections["module"], page_ids, control_ids, api_ids)
    _check_relationships(report, relationships, entity_ids)
    _check_evidence_summary(report, data, collections, relationships)
    _check_fusion_metadata(report, data)
    _check_privacy(report, data)

    counts = {key: len(value) for key, value in collections.items()}
    counts["relationship"] = len(relationships)
    checks_run = [
        "structure", "references", "evidence", "vocabulary", "geometry",
        "confidence", "honesty", "duplication", "privacy", "summary", "metadata",
    ]
    return _finalize(report, counts, checks_run)


def _finalize(report: _Report, counts: Dict[str, int], checks_run: List[str]) -> Dict[str, Any]:
    result = {
        "valid": not report.errors,
        "error_count": len(report.errors) + report.errors_truncated,
        "warning_count": len(report.warnings) + report.warnings_truncated,
        "errors": report.errors,
        "warnings": report.warnings,
        "checks_run": checks_run,
        "counts": counts,
    }
    if report.errors_truncated:
        result["errors_truncated"] = report.errors_truncated
    if report.warnings_truncated:
        result["warnings_truncated"] = report.warnings_truncated
    return result


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_ids(report: _Report, collections: Dict[str, List[Any]],
               relationships: List[Any]) -> set:
    """Ids must exist, be unique across the whole model, and look canonical."""
    seen: Dict[str, str] = {}
    entity_ids: set = set()

    for entity_type, items in collections.items():
        if not isinstance(items, list):
            report.error("E_COLLECTION_TYPE", f"'{entity_type}s' must be a list.", entity_type)
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                report.error("E_ENTITY_TYPE", f"{entity_type}[{index}] is not a mapping.", entity_type)
                continue
            entity_id = item.get("id")
            if not entity_id or not isinstance(entity_id, str):
                report.error("E_MISSING_ID", f"{entity_type}[{index}] has no id.", entity_type, None, "id")
                continue
            if entity_id in seen:
                report.error(
                    "E_DUPLICATE_ID",
                    f"id '{entity_id}' is used by both {seen[entity_id]} and {entity_type}.",
                    entity_type, entity_id, "id",
                )
            else:
                seen[entity_id] = entity_type
            entity_ids.add(entity_id)
            pattern = _ID_PATTERNS.get(entity_type)
            if pattern and not pattern.match(entity_id):
                report.warn(
                    "W_ID_FORMAT",
                    f"{entity_type} id '{entity_id}' does not match the expected "
                    f"'{pattern.pattern}' convention.",
                    entity_type, entity_id, "id",
                )

    rel_ids: set = set()
    for index, rel in enumerate(relationships):
        if not isinstance(rel, dict):
            report.error("E_ENTITY_TYPE", f"relationship[{index}] is not a mapping.", "relationship")
            continue
        rel_id = rel.get("id")
        if not rel_id:
            report.error("E_MISSING_ID", f"relationship[{index}] has no id.", "relationship", None, "id")
            continue
        if rel_id in rel_ids or rel_id in seen:
            report.error("E_DUPLICATE_ID", f"relationship id '{rel_id}' is not unique.",
                         "relationship", rel_id, "id")
        rel_ids.add(rel_id)
    return entity_ids


def _check_common_entity_rules(report: _Report, collections: Dict[str, List[Any]],
                               page_ids: set, requirement_ids: set) -> None:
    """Rules that apply to every entity: evidence, status, honesty, confidence."""
    for entity_type, items in collections.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("id")

            # -- evidence ------------------------------------------------
            refs = item.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                report.error(
                    "E_MISSING_EVIDENCE",
                    f"{entity_type} '{entity_id}' has no evidence_refs; every unified entity "
                    "must be traceable to raw evidence.",
                    entity_type, entity_id, "evidence_refs",
                )
            else:
                for ref in refs:
                    _check_evidence_ref(report, ref, entity_type, entity_id, page_ids)

            # -- observation status --------------------------------------
            status = item.get("observation_status")
            if status not in OBSERVATION_STATUSES:
                report.error(
                    "E_INVALID_OBSERVATION_STATUS",
                    f"{entity_type} '{entity_id}' has observation_status '{status}', "
                    f"expected one of {list(OBSERVATION_STATUSES)}.",
                    entity_type, entity_id, "observation_status",
                )
            elif status == INFERRED and "inference_reason" in item and not item.get("inference_reason"):
                report.error(
                    "E_MISSING_INFERENCE_REASON",
                    f"{entity_type} '{entity_id}' is marked inferred but carries no "
                    "inference_reason.",
                    entity_type, entity_id, "inference_reason",
                )

            # -- confidence ----------------------------------------------
            if "confidence" in item:
                _check_confidence(report, item, entity_type, entity_id, status)

            # -- semantic role -------------------------------------------
            if "semantic_role" in item:
                _check_semantic_role(report, item, entity_type, entity_id)

            # -- requirement refs ----------------------------------------
            for req_id in (item.get("requirement_refs") or []):
                if req_id not in requirement_ids:
                    report.error(
                        "E_UNRESOLVED_REFERENCE",
                        f"{entity_type} '{entity_id}' references unknown requirement '{req_id}'.",
                        entity_type, entity_id, "requirement_refs",
                    )

            # -- evidence sources ----------------------------------------
            if entity_type in ("page", "control", "form", "api_endpoint"):
                for source in (item.get("evidence_sources") or []):
                    if source not in EVIDENCE_SOURCES:
                        report.warn(
                            "W_UNKNOWN_EVIDENCE_SOURCE",
                            f"{entity_type} '{entity_id}' lists unrecognised evidence source "
                            f"'{source}'.",
                            entity_type, entity_id, "evidence_sources",
                        )


def _check_evidence_ref(report: _Report, ref: Any, entity_type: str,
                        entity_id: Optional[str], page_ids: set) -> None:
    if not isinstance(ref, str) or not ref.strip():
        report.error("E_INVALID_EVIDENCE_REF",
                     f"{entity_type} '{entity_id}' has a non-string evidence_ref.",
                     entity_type, entity_id, "evidence_refs")
        return
    parts = ref.split(":")
    kind = parts[0]
    if kind not in EVIDENCE_REF_KINDS:
        report.error(
            "E_UNRESOLVED_EVIDENCE_REF",
            f"{entity_type} '{entity_id}' has evidence_ref '{ref}' with unknown kind '{kind}'; "
            f"expected one of {list(EVIDENCE_REF_KINDS)}.",
            entity_type, entity_id, "evidence_refs",
        )
        return
    if len(parts) < 2:
        report.error("E_UNRESOLVED_EVIDENCE_REF",
                     f"{entity_type} '{entity_id}' has malformed evidence_ref '{ref}'.",
                     entity_type, entity_id, "evidence_refs")
        return
    # Page-scoped kinds must resolve to a page that exists in this model.
    if kind in ("crawl", "dom", "ax", "visual", "network", "screenshot"):
        scope = parts[1]
        if scope.startswith("page_") and page_ids and scope not in page_ids:
            report.error(
                "E_UNRESOLVED_EVIDENCE_REF",
                f"{entity_type} '{entity_id}' has evidence_ref '{ref}' pointing at page "
                f"'{scope}', which is not part of the model.",
                entity_type, entity_id, "evidence_refs",
            )


def _check_confidence(report: _Report, item: Dict[str, Any], entity_type: str,
                      entity_id: Optional[str], status: Any) -> None:
    confidence = item.get("confidence")
    if confidence is None:
        if item.get("confidence_basis"):
            report.warn("W_BASIS_WITHOUT_CONFIDENCE",
                        f"{entity_type} '{entity_id}' has a confidence_basis but no confidence.",
                        entity_type, entity_id, "confidence")
        return
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        report.error("E_INVALID_CONFIDENCE",
                     f"{entity_type} '{entity_id}' confidence must be a number or null, got "
                     f"{confidence!r}.",
                     entity_type, entity_id, "confidence")
        return
    if not (0.0 <= float(confidence) <= 1.0):
        report.error("E_INVALID_CONFIDENCE",
                     f"{entity_type} '{entity_id}' confidence {confidence} is outside [0, 1].",
                     entity_type, entity_id, "confidence")
    if "confidence_basis" in item and not item.get("confidence_basis"):
        report.error(
            "E_CONFIDENCE_WITHOUT_BASIS",
            f"{entity_type} '{entity_id}' reports confidence {confidence} without a documented "
            "basis; an unexplained score is not permitted.",
            entity_type, entity_id, "confidence_basis",
        )
    if status == OBSERVED:
        report.warn(
            "W_CONFIDENCE_ON_OBSERVED",
            f"{entity_type} '{entity_id}' is directly observed but carries a fusion confidence; "
            "confidence describes inference strength, not evidence.",
            entity_type, entity_id, "confidence",
        )


def _check_semantic_role(report: _Report, item: Dict[str, Any], entity_type: str,
                         entity_id: Optional[str]) -> None:
    role = item.get("semantic_role")
    role_status = item.get("semantic_role_status")
    if role is not None and role not in SEMANTIC_ROLES:
        report.error(
            "E_INVALID_SEMANTIC_ROLE",
            f"{entity_type} '{entity_id}' has semantic_role '{role}' outside the allowed "
            f"vocabulary {list(SEMANTIC_ROLES)}.",
            entity_type, entity_id, "semantic_role",
        )
    if role_status is not None and role_status not in OBSERVATION_STATUSES:
        report.error("E_INVALID_OBSERVATION_STATUS",
                     f"{entity_type} '{entity_id}' semantic_role_status '{role_status}' is invalid.",
                     entity_type, entity_id, "semantic_role_status")
    if role_status == OBSERVED:
        report.error(
            "E_SEMANTIC_ROLE_OBSERVED",
            f"{entity_type} '{entity_id}' claims its semantic role is observed; a semantic role "
            "is always an interpretation and must be 'inferred' or 'unknown'.",
            entity_type, entity_id, "semantic_role_status",
        )
    if role is None and role_status == INFERRED:
        report.warn("W_ROLE_STATUS_MISMATCH",
                    f"{entity_type} '{entity_id}' has no semantic_role but a status of 'inferred'.",
                    entity_type, entity_id, "semantic_role_status")
    if role is not None and role_status == UNKNOWN:
        report.error(
            "E_ROLE_STATUS_MISMATCH",
            f"{entity_type} '{entity_id}' asserts semantic_role '{role}' while its "
            "semantic_role_status is 'unknown'.",
            entity_type, entity_id, "semantic_role_status",
        )


def _check_pages(report: _Report, pages: List[Any], control_ids: set,
                 api_ids: set, form_ids: set) -> None:
    seen_index: Dict[Any, str] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("id")
        if not page.get("url"):
            report.warn("W_PAGE_WITHOUT_URL", f"page '{page_id}' has no url.", "page", page_id, "url")
        index = page.get("page_index")
        if index is not None:
            if index in seen_index:
                report.error("E_DUPLICATE_PAGE_INDEX",
                             f"pages '{seen_index[index]}' and '{page_id}' both claim "
                             f"page_index {index}.", "page", page_id, "page_index")
            else:
                seen_index[index] = page_id
        for field_name, valid in (("controls", control_ids), ("forms", form_ids),
                                  ("api_endpoints", api_ids)):
            for member in (page.get(field_name) or []):
                if member not in valid:
                    report.error("E_UNRESOLVED_REFERENCE",
                                 f"page '{page_id}' lists unknown {field_name[:-1]} '{member}'.",
                                 "page", page_id, field_name)
        if page.get("page_type") and page.get("page_type_status") not in OBSERVATION_STATUSES:
            report.error("E_INVALID_OBSERVATION_STATUS",
                         f"page '{page_id}' has an invalid page_type_status.",
                         "page", page_id, "page_type_status")


def _check_controls(report: _Report, controls: List[Any], page_ids: set, form_ids: set) -> None:
    seen_dom: Dict[str, str] = {}
    seen_visual: Dict[str, str] = {}
    for control in controls:
        if not isinstance(control, dict):
            continue
        control_id = control.get("id")

        ctype = control.get("type")
        if ctype not in CONTROL_TYPES:
            report.error("E_INVALID_CONTROL_TYPE",
                         f"control '{control_id}' has type '{ctype}' outside the allowed "
                         f"vocabulary {list(CONTROL_TYPES)}.",
                         "control", control_id, "type")

        page_id = control.get("page_id")
        if page_ids and page_id not in page_ids:
            report.error("E_UNRESOLVED_REFERENCE",
                         f"control '{control_id}' references unknown page '{page_id}'.",
                         "control", control_id, "page_id")

        form_id = control.get("form_id")
        if form_id and form_id not in form_ids:
            report.error("E_UNRESOLVED_REFERENCE",
                         f"control '{control_id}' references unknown form '{form_id}'.",
                         "control", control_id, "form_id")

        if not any(control.get(k) for k in ("dom_ref", "accessibility_ref", "visual_ref")):
            report.error(
                "E_CONTROL_WITHOUT_MODALITY",
                f"control '{control_id}' has no dom_ref, accessibility_ref or visual_ref, so it "
                "cannot be traced to any modality.",
                "control", control_id, "dom_ref",
            )

        # Duplicate detection: one piece of raw evidence must yield one control.
        dom_ref = control.get("dom_ref")
        if dom_ref:
            if dom_ref in seen_dom:
                report.error(
                    "E_DUPLICATE_CONTROL",
                    f"controls '{seen_dom[dom_ref]}' and '{control_id}' both describe DOM "
                    f"evidence '{dom_ref}'; cross-modal signals must merge into one control.",
                    "control", control_id, "dom_ref",
                )
            else:
                seen_dom[dom_ref] = control_id
        visual_ref = control.get("visual_ref")
        if visual_ref:
            if visual_ref in seen_visual:
                report.error(
                    "E_DUPLICATE_CONTROL",
                    f"controls '{seen_visual[visual_ref]}' and '{control_id}' both describe "
                    f"visual evidence '{visual_ref}'.",
                    "control", control_id, "visual_ref",
                )
            else:
                seen_visual[visual_ref] = control_id

        _check_bbox(report, control.get("bbox_pixels"), "bbox_pixels", "control", control_id)
        _check_bbox(report, control.get("bbox_normalized"), "bbox_normalized", "control",
                    control_id, normalized=True)


def _check_bbox(report: _Report, bbox: Any, field_name: str, entity_type: str,
                entity_id: Optional[str], normalized: bool = False) -> None:
    if bbox is None:
        return
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        report.error("E_INVALID_BBOX",
                     f"{entity_type} '{entity_id}' {field_name} must be [x1, y1, x2, y2], got "
                     f"{bbox!r}.",
                     entity_type, entity_id, field_name)
        return
    values: List[float] = []
    for value in bbox:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            report.error("E_INVALID_BBOX",
                         f"{entity_type} '{entity_id}' {field_name} contains a non-numeric value "
                         f"{value!r}.",
                         entity_type, entity_id, field_name)
            return
        values.append(float(value))
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        report.error("E_INVALID_BBOX",
                     f"{entity_type} '{entity_id}' {field_name} {values} is degenerate or "
                     "inverted (requires x1 < x2 and y1 < y2).",
                     entity_type, entity_id, field_name)
    if normalized and any(v < 0.0 or v > 1.0 for v in values):
        report.error("E_INVALID_BBOX",
                     f"{entity_type} '{entity_id}' {field_name} {values} falls outside [0, 1].",
                     entity_type, entity_id, field_name)
    if not normalized and any(v < 0.0 for v in values):
        report.warn("W_NEGATIVE_BBOX",
                    f"{entity_type} '{entity_id}' {field_name} {values} contains negative "
                    "coordinates (element may be scrolled out of view).",
                    entity_type, entity_id, field_name)


def _check_forms(report: _Report, forms: List[Any], page_ids: set,
                 control_ids: set, api_ids: set) -> None:
    for form in forms:
        if not isinstance(form, dict):
            continue
        form_id = form.get("id")
        if page_ids and form.get("page_id") not in page_ids:
            report.error("E_UNRESOLVED_REFERENCE",
                         f"form '{form_id}' references unknown page '{form.get('page_id')}'.",
                         "form", form_id, "page_id")
        for field_id in (form.get("fields") or []):
            if field_id not in control_ids:
                report.error("E_UNRESOLVED_REFERENCE",
                             f"form '{form_id}' lists unknown field control '{field_id}'.",
                             "form", form_id, "fields")
        submit = form.get("submit_control")
        if submit and submit not in control_ids:
            report.error("E_UNRESOLVED_REFERENCE",
                         f"form '{form_id}' references unknown submit control '{submit}'.",
                         "form", form_id, "submit_control")
        for api_id in (form.get("observed_api_endpoints") or []):
            if api_id not in api_ids:
                report.error("E_UNRESOLVED_REFERENCE",
                             f"form '{form_id}' references unknown endpoint '{api_id}'.",
                             "form", form_id, "observed_api_endpoints")
        if not form.get("fields"):
            report.warn("W_FORM_WITHOUT_FIELDS",
                        f"form '{form_id}' has no fields; the DOM evidence listed no inputs.",
                        "form", form_id, "fields")


def _check_api_endpoints(report: _Report, endpoints: List[Any], page_ids: set) -> None:
    seen: Dict[Any, str] = {}
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        endpoint_id = endpoint.get("id")
        method = str(endpoint.get("method") or "")
        if not method:
            report.warn("W_ENDPOINT_WITHOUT_METHOD", f"endpoint '{endpoint_id}' has no method.",
                        "api_endpoint", endpoint_id, "method")
        elif method != method.upper():
            report.warn("W_ENDPOINT_METHOD_CASE",
                        f"endpoint '{endpoint_id}' method '{method}' is not upper-case.",
                        "api_endpoint", endpoint_id, "method")
        key = (method.upper(), endpoint.get("host"), endpoint.get("path"))
        if key in seen:
            report.error("E_DUPLICATE_ENDPOINT",
                         f"endpoints '{seen[key]}' and '{endpoint_id}' describe the same "
                         f"{key[0]} {key[1]}{key[2]}; observations must be merged.",
                         "api_endpoint", endpoint_id, "path")
        else:
            seen[key] = endpoint_id
        for page_id in (endpoint.get("observed_on_pages") or []):
            if page_ids and page_id not in page_ids:
                report.error("E_UNRESOLVED_REFERENCE",
                             f"endpoint '{endpoint_id}' claims observation on unknown page "
                             f"'{page_id}'.",
                             "api_endpoint", endpoint_id, "observed_on_pages")
        if not endpoint.get("observed_on_pages"):
            report.warn("W_ENDPOINT_WITHOUT_PAGE",
                        f"endpoint '{endpoint_id}' is not linked to any page.",
                        "api_endpoint", endpoint_id, "observed_on_pages")
        count = endpoint.get("observation_count")
        if isinstance(count, int) and count <= 0:
            report.warn("W_ENDPOINT_NOT_OBSERVED",
                        f"endpoint '{endpoint_id}' has observation_count {count} but is marked "
                        f"'{endpoint.get('observation_status')}'.",
                        "api_endpoint", endpoint_id, "observation_count")


def _check_user_flows(report: _Report, flows: List[Any], page_ids: set, control_ids: set,
                      api_ids: set, requirement_ids: set) -> None:
    valid_actions = {"navigate", "input", "click", "api_call", "observe"}
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_id = flow.get("id")
        if not flow.get("name"):
            report.warn("W_FLOW_WITHOUT_NAME", f"flow '{flow_id}' has no name.",
                        "user_flow", flow_id, "name")
        for field_name, valid in (("page_ids", page_ids), ("control_ids", control_ids),
                                  ("api_endpoint_ids", api_ids)):
            for member in (flow.get(field_name) or []):
                if valid and member not in valid:
                    report.error("E_UNRESOLVED_REFERENCE",
                                 f"flow '{flow_id}' references unknown {field_name[:-1]} "
                                 f"'{member}'.",
                                 "user_flow", flow_id, field_name)
        orders: List[int] = []
        for step in (flow.get("steps") or []):
            if not isinstance(step, dict):
                report.error("E_ENTITY_TYPE", f"flow '{flow_id}' has a non-mapping step.",
                             "user_flow", flow_id, "steps")
                continue
            action = step.get("action")
            if action not in valid_actions:
                report.error("E_INVALID_FLOW_ACTION",
                             f"flow '{flow_id}' step {step.get('order')} has action '{action}', "
                             f"expected one of {sorted(valid_actions)}.",
                             "user_flow", flow_id, "steps")
            status = step.get("observation_status")
            if status not in OBSERVATION_STATUSES:
                report.error("E_INVALID_OBSERVATION_STATUS",
                             f"flow '{flow_id}' step {step.get('order')} has observation_status "
                             f"'{status}'.",
                             "user_flow", flow_id, "steps")
            elif status == INFERRED and not step.get("inference_reason"):
                report.error("E_MISSING_INFERENCE_REASON",
                             f"flow '{flow_id}' step {step.get('order')} is inferred but gives no "
                             "inference_reason.",
                             "user_flow", flow_id, "steps")
            for field_name, valid in (("page_id", page_ids), ("control_id", control_ids),
                                      ("api_endpoint_id", api_ids)):
                member = step.get(field_name)
                if member and valid and member not in valid:
                    report.error("E_UNRESOLVED_REFERENCE",
                                 f"flow '{flow_id}' step {step.get('order')} references unknown "
                                 f"{field_name} '{member}'.",
                                 "user_flow", flow_id, "steps")
            order = step.get("order")
            if isinstance(order, int):
                orders.append(order)
        if orders and sorted(orders) != orders:
            report.warn("W_FLOW_STEP_ORDER",
                        f"flow '{flow_id}' steps are not listed in ascending order.",
                        "user_flow", flow_id, "steps")
        if len(set(orders)) != len(orders):
            report.error("E_DUPLICATE_FLOW_STEP_ORDER",
                         f"flow '{flow_id}' has duplicate step order values.",
                         "user_flow", flow_id, "steps")
        for req_id in (flow.get("requirement_refs") or []):
            if requirement_ids and req_id not in requirement_ids:
                report.error("E_UNRESOLVED_REFERENCE",
                             f"flow '{flow_id}' references unknown requirement '{req_id}'.",
                             "user_flow", flow_id, "requirement_refs")


def _check_modules(report: _Report, modules: List[Any], page_ids: set,
                   control_ids: set, api_ids: set) -> None:
    seen_names: Dict[str, str] = {}
    for module in modules:
        if not isinstance(module, dict):
            continue
        module_id = module.get("id")
        name = (module.get("name") or "").strip().lower()
        if not name:
            report.error("E_MODULE_WITHOUT_NAME", f"module '{module_id}' has no name.",
                         "module", module_id, "name")
        elif name in seen_names:
            report.error("E_DUPLICATE_MODULE",
                         f"modules '{seen_names[name]}' and '{module_id}' share the name "
                         f"'{module.get('name')}'.",
                         "module", module_id, "name")
        else:
            seen_names[name] = module_id
        for field_name, valid in (("pages", page_ids), ("controls", control_ids),
                                  ("api_endpoints", api_ids)):
            for member in (module.get(field_name) or []):
                if valid and member not in valid:
                    report.error("E_UNRESOLVED_REFERENCE",
                                 f"module '{module_id}' references unknown {field_name[:-1]} "
                                 f"'{member}'.",
                                 "module", module_id, field_name)


def _check_relationships(report: _Report, relationships: List[Any], entity_ids: set) -> None:
    seen: set = set()
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        rel_id = rel.get("id")
        rel_type = rel.get("relationship")
        if rel_type not in RELATIONSHIP_TYPES:
            report.error("E_INVALID_RELATIONSHIP_TYPE",
                         f"relationship '{rel_id}' has type '{rel_type}' outside the allowed "
                         f"vocabulary {list(RELATIONSHIP_TYPES)}.",
                         "relationship", rel_id, "relationship")
        source_id, target_id = rel.get("source_id"), rel.get("target_id")
        for field_name, value in (("source_id", source_id), ("target_id", target_id)):
            if not value:
                report.error("E_MISSING_REFERENCE",
                             f"relationship '{rel_id}' has no {field_name}.",
                             "relationship", rel_id, field_name)
            elif entity_ids and value not in entity_ids:
                report.error("E_UNRESOLVED_RELATIONSHIP",
                             f"relationship '{rel_id}' {field_name} '{value}' does not resolve to "
                             "any entity in the model.",
                             "relationship", rel_id, field_name)
        if source_id and source_id == target_id:
            report.warn("W_SELF_RELATIONSHIP",
                        f"relationship '{rel_id}' points '{source_id}' at itself.",
                        "relationship", rel_id, "target_id")
        key = (source_id, target_id, rel_type)
        if key in seen:
            report.warn("W_DUPLICATE_RELATIONSHIP",
                        f"relationship '{rel_id}' duplicates {rel_type} "
                        f"{source_id} -> {target_id}.",
                        "relationship", rel_id, "relationship")
        seen.add(key)

        status = rel.get("observation_status")
        if status not in OBSERVATION_STATUSES:
            report.error("E_INVALID_OBSERVATION_STATUS",
                         f"relationship '{rel_id}' has observation_status '{status}'.",
                         "relationship", rel_id, "observation_status")
        elif status == INFERRED and not rel.get("inference_reason"):
            report.error("E_MISSING_INFERENCE_REASON",
                         f"relationship '{rel_id}' is inferred but gives no inference_reason.",
                         "relationship", rel_id, "inference_reason")
        _check_confidence(report, rel, "relationship", rel_id, status)
        if rel_type in ("likely_triggers", "submits_to") and status == OBSERVED:
            report.warn(
                "W_CAUSATION_MARKED_OBSERVED",
                f"relationship '{rel_id}' asserts '{rel_type}' as observed; the crawler does not "
                "execute submissions, so this should normally be 'inferred'.",
                "relationship", rel_id, "observation_status",
            )


def _check_evidence_summary(report: _Report, data: Dict[str, Any],
                            collections: Dict[str, List[Any]], relationships: List[Any]) -> None:
    """The summary must be computed from the model, never hard-coded."""
    summary = data.get("evidence_summary")
    if not isinstance(summary, dict) or not summary:
        report.warn("W_MISSING_EVIDENCE_SUMMARY", "evidence_summary is missing or empty.")
        return
    expected = {
        "pages": len(collections["page"]),
        "controls": len(collections["control"]),
        "forms": len(collections["form"]),
        "api_endpoints": len(collections["api_endpoint"]),
        "user_flows": len(collections["user_flow"]),
        "modules": len(collections["module"]),
        "requirements": len(collections["requirement"]),
        "relationships": len(relationships),
    }
    for key, value in expected.items():
        if key in summary and summary.get(key) != value:
            report.error(
                "E_SUMMARY_MISMATCH",
                f"evidence_summary.{key} is {summary.get(key)} but the model contains {value}; "
                "counts must be computed from the actual data.",
                "evidence_summary", None, key,
            )
    status_total = sum(
        summary.get(k, 0) for k in ("observed_entities", "inferred_entities", "unknown_entities")
        if isinstance(summary.get(k), int)
    )
    entity_total = sum(len(v) for v in collections.values()) + len(relationships)
    if status_total and status_total != entity_total:
        report.warn(
            "W_STATUS_TOTAL_MISMATCH",
            f"observed+inferred+unknown = {status_total} but the model holds {entity_total} "
            "entities and relationships.",
            "evidence_summary",
        )


def _check_fusion_metadata(report: _Report, data: Dict[str, Any]) -> None:
    metadata = data.get("fusion_metadata")
    if not isinstance(metadata, dict) or not metadata:
        report.error("E_MISSING_FUSION_METADATA", "fusion_metadata is missing.", "fusion_metadata")
        return
    for key in ("fusion_version", "fusion_timestamp", "engine"):
        if not metadata.get(key):
            report.error("E_MISSING_FUSION_METADATA",
                         f"fusion_metadata.{key} is missing.", "fusion_metadata", None, key)
    engine = metadata.get("engine")
    llm_used = metadata.get("llm_used")
    if engine == "deterministic" and llm_used:
        report.error(
            "E_ENGINE_CLAIM_MISMATCH",
            "fusion_metadata claims engine 'deterministic' while llm_used is true; the reported "
            "engine must match how the model was actually produced.",
            "fusion_metadata", None, "llm_used",
        )
    if not isinstance(metadata.get("sources"), list) or not metadata.get("sources"):
        report.warn("W_NO_SOURCES", "fusion_metadata.sources is empty.",
                    "fusion_metadata", None, "sources")


def _check_privacy(report: _Report, data: Dict[str, Any]) -> None:
    """
    Phase 1.5F §39 — no credentials, no tokens, no headers, no embedded images.

    Only *keys* are matched against the credential pattern: a control labelled
    "Password" is legitimate UI metadata, while a key named ``password`` would
    mean a value was copied in.
    """
    findings: List[str] = []

    def walk(node: Any, path: str, depth: int = 0) -> None:
        if depth > 12 or len(findings) > 50:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and FORBIDDEN_KEY_PATTERN.search(key):
                    report.error(
                        "E_SENSITIVE_DATA",
                        f"'{key_path}' uses a credential/header-shaped key; passwords, tokens, "
                        "cookies, API keys and raw headers must never be copied into the unified "
                        "model.",
                        "privacy", None, key_path,
                    )
                    findings.append(key_path)
                walk(value, key_path, depth + 1)
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node[:200]):
                walk(value, f"{path}[{index}]", depth + 1)
        elif isinstance(node, str):
            if EMBEDDED_IMAGE_PATTERN.search(node):
                report.error(
                    "E_EMBEDDED_IMAGE_DATA",
                    f"'{path}' embeds image data; visual evidence must reference the screenshot "
                    "artifact instead.",
                    "privacy", None, path,
                )
                findings.append(path)
            elif len(node) > MAX_STRING_VALUE_LENGTH:
                report.warn(
                    "W_LARGE_PAYLOAD",
                    f"'{path}' holds {len(node)} characters; the unified model should reference "
                    "raw evidence rather than duplicating it.",
                    "privacy", None, path,
                )

    walk(data, "")
