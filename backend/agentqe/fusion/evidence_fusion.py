"""
Phase 1.5F — Deterministic cross-modal evidence fusion engine.

Consumes the evidence already collected by phases 1.5A–1.5E plus requirement
and repository analysis, and produces a ``UnifiedApplicationModel``.

Guarantees
----------
* **Deterministic** — no LLM, no network, no randomness. The same
  ApplicationContext always yields the same model (ids included).
* **Non-destructive** — the ApplicationContext and its raw evidence are never
  mutated; the unified model only *references* them.
* **Traceable** — every entity carries ``evidence_refs``.
* **Honest** — ``observed`` / ``inferred`` / ``unknown`` are distinguished,
  semantic roles are ``None`` when unsupported, and confidence is ``None``
  unless a documented formula produced it.

Evidence reference grammar
--------------------------
``crawl:page_001``                      the CrawledPage itself
``dom:page_001:element_005``            ApplicationContext.pages[0].dom.interactive_elements[5]
``dom:page_001:form_002``               ...dom.forms[2]
``dom:page_001:form_002:input_001``     ...dom.forms[2].inputs[1]
``ax:page_001:node_014``                14th node of the DFS-flattened accessibility tree
``visual:page_001:visual_003``          ...visual_ui.elements[3]
``network:page_001:req_007``            ...network_activity[7]
``screenshot:page_001``                 ...screenshot (artifact metadata, never image bytes)
``requirement:REQ-002``                 normalized requirement
``repository:file_003``                 normalized repository source entry
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from agentqe.fusion.confidence import (
    correlation_confidence,
    flow_confidence,
    ui_api_confidence,
)
from agentqe.fusion.correlators import (
    ax_role_control_type,
    correlate_ax_to_dom,
    correlate_visual_to_dom,
    dom_bbox_to_xyxy,
    dom_control_type,
    dom_element_key,
    dom_element_label,
    flatten_ax_tree,
    normalize_bbox,
    normalize_text,
    text_similarity,
    tokenize,
    visual_control_type,
    visual_element_text,
)
from agentqe.fusion.interfaces import EvidenceFusionEngine
from agentqe.fusion.schemas import (
    FUSION_VERSION,
    INFERRED,
    OBSERVED,
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limits — fusion must stay lightweight compared with crawling / OmniParser
# ---------------------------------------------------------------------------

@dataclass
class FusionLimits:
    max_pages: int = 100
    max_controls_per_page: int = 300
    max_controls_total: int = 3000
    max_forms_total: int = 300
    max_api_endpoints: int = 500
    max_relationships: int = 8000
    max_evidence_refs_per_entity: int = 12
    max_user_flows: int = 60
    max_modules: int = 50
    max_requirements: int = 200
    max_repository_sources: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_pages": self.max_pages,
            "max_controls_per_page": self.max_controls_per_page,
            "max_controls_total": self.max_controls_total,
            "max_forms_total": self.max_forms_total,
            "max_api_endpoints": self.max_api_endpoints,
            "max_relationships": self.max_relationships,
            "max_evidence_refs_per_entity": self.max_evidence_refs_per_entity,
            "max_user_flows": self.max_user_flows,
            "max_modules": self.max_modules,
            "max_requirements": self.max_requirements,
            "max_repository_sources": self.max_repository_sources,
        }


# ---------------------------------------------------------------------------
# Small vocabularies used by the conservative semantic rules
# ---------------------------------------------------------------------------

_SUBMIT_LABEL_WORDS = {
    "submit", "send", "continue", "next", "save", "confirm", "apply", "ok",
}
_AUTH_LABEL_WORDS = {
    "login", "log", "signin", "sign", "authenticate", "register", "signup",
}
_AUTH_PATH_WORDS = {
    "login", "signin", "auth", "authenticate", "session", "sessions", "token",
    "oauth", "logon", "authorize", "identity",
}
_SEARCH_WORDS = {"search", "find", "query", "lookup"}
_USERNAME_NAME_WORDS = {"user", "username", "email", "login", "userid", "user_name", "account"}

#: Semantic roles that describe a control which *performs* an action. Only these
#: may be associated with an API endpoint via ``likely_triggers``.
_ACTION_SEMANTIC_ROLES = {"authentication_submit", "search_submit", "form_submit"}

_STOPWORD_TOKENS = {
    "page", "home", "index", "the", "and", "for", "with", "app", "web", "www",
    "com", "http", "https", "html", "php", "aspx", "jsx", "tsx", "js", "ts",
    "py", "src", "main", "test", "new", "get", "set", "api", "v1", "v2",
}

_MIN_TOKEN_LEN = 4


def _significant_tokens(*values: Any) -> List[str]:
    """Tokens long enough and specific enough to justify an association."""
    out: List[str] = []
    for value in values:
        if not value:
            continue
        for token in tokenize(str(value)):
            if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORD_TOKENS and token not in out:
                out.append(token)
    return out


def _path_tokens(path: str) -> List[str]:
    return [t for t in tokenize(path or "") if t]


# ---------------------------------------------------------------------------
# Fusion state
# ---------------------------------------------------------------------------

@dataclass
class _State:
    model: UnifiedApplicationModel = field(default_factory=UnifiedApplicationModel)
    warnings: List[str] = field(default_factory=list)
    control_seq: int = 0
    form_seq: int = 0
    api_seq: int = 0
    rel_seq: int = 0
    flow_seq: int = 0
    module_seq: int = 0
    # page_id -> list of control ids
    page_controls: Dict[str, List[str]] = field(default_factory=dict)
    # page_id -> page dict (raw evidence, read-only)
    raw_pages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # lookup for navigation edges
    url_to_page: Dict[str, str] = field(default_factory=dict)
    # repository sources: id -> {"file": ...}
    repository_sources: List[Dict[str, Any]] = field(default_factory=list)
    # statistics
    stats: Dict[str, int] = field(default_factory=dict)

    def bump(self, key: str, amount: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + amount


class DeterministicEvidenceFusionEngine(EvidenceFusionEngine):
    """
    Rule-based, explainable fusion engine (Phase 1.5F default).

    No LLM / VLM / RAG / embedding is used. A future semantic engine can
    implement ``EvidenceFusionEngine`` and consume this model as its input.
    """

    engine_name = "deterministic"

    def __init__(self, limits: Optional[FusionLimits] = None):
        self.limits = limits or FusionLimits()

    # -- public API ---------------------------------------------------------

    def get_engine_info(self) -> Dict[str, Any]:
        return {
            "engine": self.engine_name,
            "fusion_version": FUSION_VERSION,
            "llm_used": False,
            "deterministic": True,
        }

    def fuse(self, application_context: Any) -> UnifiedApplicationModel:
        started = time.time()
        ctx = self._as_dict(application_context)
        state = _State()

        self._fuse_requirements(ctx, state)
        self._index_repository(ctx, state)
        self._fuse_pages(ctx, state)
        self._fuse_api_endpoints(ctx, state)
        self._link_forms_and_controls_to_apis(state)
        self._fuse_navigation(ctx, state)
        self._fuse_user_flows(ctx, state)
        self._fuse_modules(ctx, state)
        self._apply_requirement_traceability(state)
        self._apply_repository_traceability(state)
        self._build_application(ctx, state)
        self._build_evidence_summary(ctx, state)

        model = state.model
        model.fusion_metadata = FusionMetadata(
            fusion_version=FUSION_VERSION,
            fusion_timestamp=datetime.now(timezone.utc).isoformat(),
            engine=self.engine_name,
            llm_used=False,
            sources=self._detected_sources(ctx, state),
            duration_ms=round((time.time() - started) * 1000, 2),
            limits=self.limits.to_dict(),
            warnings=state.warnings,
        )
        return model

    # -- context access -----------------------------------------------------

    @staticmethod
    def _as_dict(application_context: Any) -> Dict[str, Any]:
        """Accept an ApplicationContext dataclass, a dict, or None."""
        if application_context is None:
            return {}
        if isinstance(application_context, dict):
            return application_context
        to_dict = getattr(application_context, "to_dict", None)
        if callable(to_dict):
            try:
                return to_dict()
            except Exception:  # pragma: no cover - defensive
                pass
        return {
            k: v for k, v in vars(application_context).items()
            if not k.startswith("_")
        }

    # -- ids ----------------------------------------------------------------

    @staticmethod
    def _page_id(index: int) -> str:
        return f"page_{index + 1:03d}"

    def _next_control_id(self, state: _State) -> str:
        state.control_seq += 1
        return f"control_{state.control_seq:03d}"

    def _next_form_id(self, state: _State) -> str:
        state.form_seq += 1
        return f"form_{state.form_seq:03d}"

    def _next_api_id(self, state: _State) -> str:
        state.api_seq += 1
        return f"api_{state.api_seq:03d}"

    def _next_flow_id(self, state: _State) -> str:
        state.flow_seq += 1
        return f"flow_{state.flow_seq:03d}"

    def _next_module_id(self, state: _State) -> str:
        state.module_seq += 1
        return f"module_{state.module_seq:03d}"

    def _add_relationship(
        self,
        state: _State,
        source_id: str,
        target_id: str,
        relationship: str,
        observation_status: str,
        evidence_refs: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        confidence_basis: Optional[str] = None,
        inference_reason: Optional[str] = None,
    ) -> Optional[Relationship]:
        if len(state.model.relationships) >= self.limits.max_relationships:
            if "relationship_limit_reached" not in state.stats:
                state.warnings.append(
                    f"Relationship limit ({self.limits.max_relationships}) reached; "
                    "further relationships were not emitted."
                )
            state.bump("relationship_limit_reached")
            return None
        state.rel_seq += 1
        rel = Relationship(
            id=f"rel_{state.rel_seq:03d}",
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            observation_status=observation_status,
            confidence=confidence,
            confidence_basis=confidence_basis,
            inference_reason=inference_reason,
            evidence_refs=(evidence_refs or [])[: self.limits.max_evidence_refs_per_entity],
        )
        state.model.relationships.append(rel)
        return rel

    @staticmethod
    def _mark_merged(control: UnifiedControl, reason: str) -> None:
        """
        Record a derived attribute or a cross-modal identity claim on a control.

        The control's *existence* stays observed — that is conveyed by
        ``evidence_sources``, the per-modality refs and the page ``contains``
        relationship. ``observation_status`` describes the entity *as asserted
        here*, so as soon as fusion adds something it derived (a semantic role, a
        type taken from an AX role, a scored visual merge) the status becomes
        ``inferred`` and the reason is appended.
        """
        control.observation_status = INFERRED
        if control.inference_reason:
            if reason not in control.inference_reason:
                control.inference_reason = f"{control.inference_reason} {reason}"
        else:
            control.inference_reason = reason

    # ------------------------------------------------------------------
    # 1. Requirements
    # ------------------------------------------------------------------

    def _fuse_requirements(self, ctx: Dict[str, Any], state: _State) -> None:
        """
        Normalize requirements into stable deterministic ids (REQ-001, ...).

        Ids are assigned in source order so they remain stable for the same
        ApplicationContext. An id already present on a requirement is reused.
        """
        raw = ctx.get("requirements") or []
        if not isinstance(raw, list):
            return
        seen_ids: set = set()
        for idx, item in enumerate(raw[: self.limits.max_requirements]):
            if isinstance(item, dict):
                description = str(
                    item.get("description") or item.get("text") or item.get("requirement") or ""
                ).strip()
                source = str(item.get("source") or "requirement_analysis")
                existing_id = item.get("id")
            else:
                description = str(item).strip()
                source = "requirement_analysis"
                existing_id = None
            if not description:
                continue
            req_id = str(existing_id) if existing_id else f"REQ-{idx + 1:03d}"
            if req_id in seen_ids:
                req_id = f"REQ-{idx + 1:03d}"
            seen_ids.add(req_id)
            state.model.requirements.append(UnifiedRequirement(
                id=req_id,
                description=description[:1000],
                source=source,
                keywords=_significant_tokens(description)[:25],
                observation_status=OBSERVED,
                evidence_refs=[evidence_ref("requirement", req_id)],
            ))

    # ------------------------------------------------------------------
    # 2. Repository index
    # ------------------------------------------------------------------

    def _index_repository(self, ctx: Dict[str, Any], state: _State) -> None:
        """
        Index whatever the repository analysis actually returned. Nothing is
        invented: only file paths present in the context are used.
        """
        files: List[str] = []
        for value in (ctx.get("source_files") or []):
            if isinstance(value, str) and value.strip():
                files.append(value.strip())
            elif isinstance(value, dict):
                path = value.get("path") or value.get("file") or value.get("name")
                if path:
                    files.append(str(path))

        repo_data = ctx.get("repository_data") or {}
        analysis = repo_data.get("analysis") if isinstance(repo_data, dict) else {}
        if isinstance(analysis, dict):
            for key in ("key_files", "files", "routes", "components", "services", "controllers"):
                for value in (analysis.get(key) or []):
                    if isinstance(value, str) and value.strip():
                        files.append(value.strip())
                    elif isinstance(value, dict):
                        path = value.get("path") or value.get("file") or value.get("name")
                        if path:
                            files.append(str(path))

        seen: set = set()
        for path in files:
            if path in seen:
                continue
            seen.add(path)
            if len(state.repository_sources) >= self.limits.max_repository_sources:
                break
            idx = len(state.repository_sources)
            stem = path.replace("\\", "/").rstrip("/").split("/")[-1]
            symbol = stem.rsplit(".", 1)[0] if "." in stem else stem
            state.repository_sources.append({
                "id": f"file_{idx + 1:03d}",
                "file": path,
                "symbol": symbol,
                "tokens": _significant_tokens(symbol),
                "evidence_ref": evidence_ref("repository", f"file_{idx + 1:03d}"),
            })

    # ------------------------------------------------------------------
    # 3. Pages, controls and forms
    # ------------------------------------------------------------------

    def _fuse_pages(self, ctx: Dict[str, Any], state: _State) -> None:
        pages = ctx.get("pages") or []
        if not isinstance(pages, list):
            return
        if len(pages) > self.limits.max_pages:
            state.warnings.append(
                f"ApplicationContext has {len(pages)} pages; only the first "
                f"{self.limits.max_pages} were fused."
            )
        for index, raw_page in enumerate(pages[: self.limits.max_pages]):
            page = self._as_dict(raw_page)
            if not isinstance(page, dict):
                continue
            page_id = self._page_id(index)
            state.raw_pages[page_id] = page

            url = str(page.get("url") or "")
            screenshot = page.get("screenshot") or {}
            visual_ui = page.get("visual_ui") or {}

            unified_page = UnifiedPage(
                id=page_id,
                url=url,
                normalized_url=self._normalize_url(url),
                title=(page.get("title") or None),
                page_type=(page.get("page_type") or None),
                page_type_status=(
                    OBSERVED if page.get("page_type_confidence") == "observed" else INFERRED
                ),
                depth=page.get("depth"),
                crawl_status=str(page.get("crawl_status") or "unknown"),
                observed=True,
                observation_status=OBSERVED,
                page_index=index,
                crawl_ref=evidence_ref("crawl", page_id),
                screenshot_ref=(
                    evidence_ref("screenshot", page_id)
                    if isinstance(screenshot, dict) and screenshot.get("status") == "success"
                    else None
                ),
                visual_ui_status=(visual_ui.get("status") if isinstance(visual_ui, dict) else None),
                evidence_refs=[evidence_ref("crawl", page_id)],
                evidence_sources=["crawl"],
            )

            for key, source in (("dom", "dom"), ("accessibility_tree", "accessibility"),
                                ("network_activity", "network")):
                if page.get(key):
                    unified_page.evidence_sources.append(source)
            if unified_page.screenshot_ref:
                unified_page.evidence_sources.append("screenshot")
                unified_page.evidence_refs.append(unified_page.screenshot_ref)
            if isinstance(visual_ui, dict) and visual_ui.get("status") == "success":
                unified_page.evidence_sources.append("visual_ui")

            state.model.pages.append(unified_page)
            state.page_controls[page_id] = []

            if page.get("crawl_status") not in (None, "", "success"):
                # Failed pages are still recorded (they are observed facts) but
                # carry no DOM/visual evidence to fuse.
                state.bump("pages_not_successful")

            self._fuse_page_controls(page, page_id, unified_page, state)
            self._fuse_page_forms(page, page_id, unified_page, state)

    # -- controls -----------------------------------------------------------

    def _fuse_page_controls(
        self,
        page: Dict[str, Any],
        page_id: str,
        unified_page: UnifiedPage,
        state: _State,
    ) -> None:
        dom = page.get("dom") or {}
        dom_elements_raw = []
        if isinstance(dom, dict):
            dom_elements_raw = dom.get("interactive_elements") or dom.get("elements") or []
        if not isinstance(dom_elements_raw, list):
            dom_elements_raw = []

        # De-duplicate identical DOM records (the crawler unions several
        # selectors, so the same node can appear twice).
        dom_elements: List[Dict[str, Any]] = []
        dom_indexes: List[int] = []
        seen_keys: set = set()
        for raw_index, element in enumerate(dom_elements_raw):
            if not isinstance(element, dict):
                continue
            key = dom_element_key(element, raw_index)
            if key in seen_keys:
                state.bump("duplicate_dom_elements_skipped")
                continue
            seen_keys.add(key)
            dom_elements.append(element)
            dom_indexes.append(raw_index)
            if len(dom_elements) >= self.limits.max_controls_per_page:
                break

        state.bump("dom_controls", len(dom_elements))

        # Accessibility correlation
        ax_nodes = flatten_ax_tree(page.get("accessibility_tree"))
        state.bump("accessibility_nodes", len(ax_nodes))
        ax_matches = correlate_ax_to_dom(dom_elements, ax_nodes) if ax_nodes else {}

        # Geometry preparation for visual correlation
        image_w, image_h, bbox_reliable, geometry_note = self._screenshot_geometry(page)
        dom_bboxes_norm: List[Optional[List[float]]] = []
        dom_bboxes_px: List[Optional[List[float]]] = []
        for element in dom_elements:
            px = dom_bbox_to_xyxy(element.get("bounding_box"))
            dom_bboxes_px.append(px)
            dom_bboxes_norm.append(normalize_bbox(px, image_w, image_h))

        # Build one control per DOM element
        control_ids: List[str] = []
        for local_index, element in enumerate(dom_elements):
            if state.control_seq >= self.limits.max_controls_total:
                state.warnings.append(
                    f"Control limit ({self.limits.max_controls_total}) reached; "
                    "some DOM elements were not fused."
                )
                break
            raw_index = dom_indexes[local_index]
            control_id = self._next_control_id(state)
            dom_ref = evidence_ref("dom", page_id, f"element_{raw_index:03d}")

            label = dom_element_label(element)
            control = UnifiedControl(
                id=control_id,
                type=dom_control_type(element),
                label=label or None,
                text=(element.get("text") or None),
                observation_status=OBSERVED,
                semantic_role=None,
                semantic_role_status=UNKNOWN,
                interactable=(not bool(element.get("disabled"))),
                page_id=page_id,
                dom_ref=dom_ref,
                dom_id=(element.get("id") or None),
                dom_tag=(element.get("tag") or None),
                dom_name=(element.get("name") or None),
                dom_type=(element.get("type") or None),
                role=(element.get("role") or None),
                href=(element.get("href") or None),
                bbox_pixels=dom_bboxes_px[local_index],
                bbox_normalized=dom_bboxes_norm[local_index],
                evidence_refs=[dom_ref, evidence_ref("crawl", page_id)],
                evidence_sources=["dom", "crawl"],
            )

            # Accessibility correlation
            match = ax_matches.get(local_index)
            if match:
                ax_ref = evidence_ref("ax", page_id, f"node_{match['ax_index']:03d}")
                control.accessibility_ref = ax_ref
                control.evidence_refs.append(ax_ref)
                control.evidence_sources.append("accessibility")
                control.correlation["accessibility"] = {
                    "ax_index": match["ax_index"],
                    "score": match["score"],
                    "role": match.get("role"),
                    "name": match.get("name"),
                }
                if not control.label and match.get("name"):
                    control.label = str(match["name"])
                if control.type == "other":
                    ax_type = ax_role_control_type(match.get("role"))
                    if ax_type != "other":
                        control.type = ax_type
                        self._mark_merged(control, (
                            f"Control type derived from accessibility role "
                            f"'{match.get('role')}' because the DOM tag was ambiguous."
                        ))
                # An exact name+role agreement is treated as corroboration of an
                # observed fact; a fuzzy match is a scored identity claim and is
                # therefore recorded as an inference.
                if float(match.get("score") or 0.0) < 0.999:
                    self._mark_merged(control, (
                        f"Accessibility node {match['ax_index']} associated with this DOM element "
                        f"by name/role similarity (matching score {round(float(match['score']), 4)})."
                    ))
                state.bump("controls_with_accessibility")

            if control.label is None and control.text is None:
                # Detected, but nothing describes it.
                control.observation_status = UNKNOWN if control.type == "other" else control.observation_status

            state.model.controls.append(control)
            control_ids.append(control_id)
            self._add_relationship(
                state, page_id, control_id, "contains", OBSERVED,
                evidence_refs=[dom_ref, evidence_ref("crawl", page_id)],
            )

        # Visual correlation
        self._correlate_visual_elements(
            page=page,
            page_id=page_id,
            state=state,
            dom_elements=dom_elements,
            dom_indexes=dom_indexes,
            dom_bboxes_norm=dom_bboxes_norm,
            control_ids=control_ids,
            bbox_reliable=bbox_reliable,
            geometry_note=geometry_note,
            image_w=image_w,
            image_h=image_h,
        )

        state.page_controls[page_id] = list(control_ids)
        unified_page.controls = list(control_ids)

        # Semantic roles need the page's full control set, so infer last.
        self._infer_control_semantic_roles(page, page_id, state)

    def _screenshot_geometry(self, page: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], bool, str]:
        """
        Determine the coordinate space shared by DOM rects and visual boxes.

        DOM ``getBoundingClientRect`` is viewport-relative. A *viewport*
        screenshot therefore shares the DOM coordinate space; a *full_page*
        screenshot does not (content below the fold shifts), so bounding-box
        agreement is marked unreliable and the score falls back to text + role.
        """
        screenshot = page.get("screenshot") or {}
        visual = page.get("visual_ui") or {}
        capture_type = screenshot.get("capture_type") if isinstance(screenshot, dict) else None

        viewport = screenshot.get("viewport") if isinstance(screenshot, dict) else None
        image_w = image_h = None
        note = ""

        if capture_type == "viewport" and isinstance(viewport, dict):
            image_w, image_h = viewport.get("width"), viewport.get("height")
            reliable = True
            note = "viewport screenshot: DOM rects and visual boxes share a coordinate space"
        elif capture_type == "viewport":
            image_w = (visual.get("image_width") if isinstance(visual, dict) else None) or \
                      (screenshot.get("width") if isinstance(screenshot, dict) else None)
            image_h = (visual.get("image_height") if isinstance(visual, dict) else None) or \
                      (screenshot.get("height") if isinstance(screenshot, dict) else None)
            reliable = True
            note = "viewport screenshot: image dimensions used to normalize DOM rects"
        else:
            image_w = (visual.get("image_width") if isinstance(visual, dict) else None) or \
                      (screenshot.get("width") if isinstance(screenshot, dict) else None)
            image_h = (visual.get("image_height") if isinstance(visual, dict) else None) or \
                      (screenshot.get("height") if isinstance(screenshot, dict) else None)
            reliable = False
            note = (
                f"capture_type={capture_type or 'unknown'}: DOM viewport rects are not "
                "comparable with full-page image coordinates, so bbox agreement was "
                "excluded from the correlation score"
            )
        return image_w, image_h, reliable, note

    def _correlate_visual_elements(
        self,
        page: Dict[str, Any],
        page_id: str,
        state: _State,
        dom_elements: List[Dict[str, Any]],
        dom_indexes: List[int],
        dom_bboxes_norm: List[Optional[List[float]]],
        control_ids: List[str],
        bbox_reliable: bool,
        geometry_note: str,
        image_w: Optional[int],
        image_h: Optional[int],
    ) -> None:
        visual = page.get("visual_ui") or {}
        if not isinstance(visual, dict) or visual.get("status") != "success":
            return
        elements = visual.get("elements") or []
        if not isinstance(elements, list) or not elements:
            return
        state.bump("visual_elements", len(elements))

        matches = correlate_visual_to_dom(
            visual_elements=elements,
            dom_elements=dom_elements,
            dom_bboxes_normalized=dom_bboxes_norm,
            bbox_reliable=bbox_reliable,
        )

        for record in matches:
            v_index = record["visual_index"]
            visual_element = elements[v_index] if v_index < len(elements) else {}
            v_id = visual_element.get("id") or f"visual_{v_index:03d}"
            v_ref = evidence_ref("visual", page_id, str(v_id))

            dom_index = record.get("dom_index")
            if dom_index is not None and dom_index < len(control_ids):
                control = state.model.control_by_id(control_ids[dom_index])
                if control is None:
                    continue
                control.visual_ref = v_ref
                control.evidence_refs.append(v_ref)
                control.evidence_sources.append("visual_ui")
                conf, basis = correlation_confidence(record.get("score"), record.get("signals"))
                control.confidence = conf
                control.confidence_basis = basis
                control.correlation["visual"] = {
                    "visual_index": v_index,
                    "visual_id": v_id,
                    "match": "matched",
                    "score": record.get("score"),
                    "signals": record.get("signals"),
                    "geometry": geometry_note,
                }
                if not control.bbox_pixels and visual_element.get("bbox_pixels"):
                    control.bbox_pixels = list(visual_element.get("bbox_pixels") or []) or None
                if not control.bbox_normalized and visual_element.get("bbox_normalized"):
                    control.bbox_normalized = list(visual_element.get("bbox_normalized") or []) or None
                self._mark_merged(control, (
                    f"Visual element '{v_id}' merged into this DOM control by deterministic "
                    f"text/geometry/role correlation (matching score {record.get('score')}); "
                    "the identity claim is an inference, the individual observations are not."
                ))
                state.bump("controls_with_visual_correlation")
                continue

            # No confident match -> keep the visual observation as its own record
            # rather than forcing it onto a DOM element.
            ambiguous = bool(record.get("ambiguous"))
            if ambiguous:
                state.bump("ambiguous_visual_matches")

            if state.control_seq >= self.limits.max_controls_total:
                continue

            v_text = visual_element_text(visual_element)
            v_type = visual_control_type(visual_element.get("type"))
            control_id = self._next_control_id(state)
            control = UnifiedControl(
                id=control_id,
                type=v_type,
                label=(v_text or None),
                text=(visual_element.get("text") or None),
                observation_status=(OBSERVED if v_text or v_type != "other" else UNKNOWN),
                semantic_role=None,
                semantic_role_status=UNKNOWN,
                interactable=visual_element.get("interactable"),
                page_id=page_id,
                visual_ref=v_ref,
                bbox_pixels=(list(visual_element.get("bbox_pixels") or []) or None),
                bbox_normalized=(list(visual_element.get("bbox_normalized") or []) or None),
                evidence_refs=[v_ref, evidence_ref("crawl", page_id)],
                evidence_sources=["visual_ui", "crawl"],
                correlation={
                    "visual": {
                        "visual_index": v_index,
                        "visual_id": v_id,
                        "match": "ambiguous" if ambiguous else "none",
                        "score": record.get("score"),
                        "signals": record.get("signals"),
                        "geometry": geometry_note,
                        "candidates": record.get("candidates"),
                    }
                },
                inference_reason=(
                    "Visual element could not be uniquely correlated with a DOM element "
                    "(runner-up within the ambiguity margin); kept as a separate visual "
                    "observation instead of forcing a match."
                    if ambiguous else
                    "Visual element had no DOM counterpart above the correlation threshold; "
                    "kept as a visual-only observation."
                ),
            )
            state.model.controls.append(control)
            state.page_controls.setdefault(page_id, [])
            control_ids.append(control_id)
            state.bump("visual_only_controls")
            self._add_relationship(
                state, page_id, control_id, "contains", OBSERVED,
                evidence_refs=[v_ref, evidence_ref("crawl", page_id)],
            )

            # Record the uncertainty explicitly instead of hiding it.
            if ambiguous:
                for candidate in (record.get("candidates") or [])[:3]:
                    c_index = candidate.get("dom_index")
                    if c_index is None or c_index >= len(control_ids):
                        continue
                    other_id = control_ids[c_index]
                    if other_id == control_id:
                        continue
                    self._add_relationship(
                        state, control_id, other_id, "observed_with", UNKNOWN,
                        evidence_refs=[v_ref],
                        confidence=None,
                        inference_reason=(
                            f"Ambiguous visual/DOM correlation (matching score "
                            f"{candidate.get('score')}); relationship left uncertain."
                        ),
                    )

    # -- semantic roles ------------------------------------------------------

    def _infer_control_semantic_roles(self, page: Dict[str, Any], page_id: str, state: _State) -> None:
        """
        Conservative semantic role inference.

        A role is only assigned when a concrete signal supports it, and the role
        is always recorded as ``inferred`` (never ``observed``) because it is an
        interpretation of the evidence, not the evidence itself.
        """
        controls = [c for c in state.model.controls if c.page_id == page_id]
        if not controls:
            return

        page_has_password = any((c.dom_type or "").lower() == "password" for c in controls)
        api_paths = self._page_api_paths(page)
        auth_endpoint = next(
            (p for p in api_paths if any(w in _path_tokens(p) for w in _AUTH_PATH_WORDS)), None
        )

        for control in controls:
            dom_type = (control.dom_type or "").lower()
            label_tokens = set(tokenize(control.label or ""))
            role, reason = None, None

            if dom_type == "password":
                role = "authentication_password"
                reason = "DOM input type=password observed."
            elif dom_type == "search" or (control.role or "").lower() == "searchbox":
                role = "search_input"
                reason = "DOM input type=search / role=searchbox observed."
            elif control.type == "input" and page_has_password and (
                dom_type == "email"
                or any(w in _USERNAME_NAME_WORDS for w in tokenize(control.dom_name or ""))
                or any(w in _USERNAME_NAME_WORDS for w in label_tokens)
            ):
                role = "authentication_username"
                reason = (
                    "Text/email input whose name or label matches an identity field, on a page "
                    "where a password input was also observed."
                )
            elif control.type == "input" and (label_tokens & _SEARCH_WORDS):
                role = "search_input"
                reason = "Input label/placeholder contains a search term."
            elif control.type == "button":
                if page_has_password and (label_tokens & _AUTH_LABEL_WORDS):
                    role = "authentication_submit"
                    reason = (
                        f"Button label '{control.label}' correlates with a password input "
                        "observed on the same page."
                    )
                    if auth_endpoint:
                        reason += f" An authentication-shaped endpoint ({auth_endpoint}) was also observed on this page."
                elif label_tokens & _SEARCH_WORDS:
                    role = "search_submit"
                    reason = "Button label contains a search term."
                elif label_tokens & _SUBMIT_LABEL_WORDS or dom_type == "submit":
                    role = "form_submit"
                    reason = (
                        "Button is a submit control (type=submit or submit-style label)."
                        if dom_type == "submit" else
                        "Button label matches a generic submit action."
                    )
            elif control.type == "link" and control.href:
                if self._is_nav_link(page, control):
                    role = "navigation_link"
                    reason = "Anchor observed inside a navigation landmark / nav link set."

            if role:
                control.semantic_role = role
                control.semantic_role_status = INFERRED
                self._mark_merged(control, (
                    f"{reason} Semantic role inferred deterministically from that evidence."
                ))
                state.bump("controls_with_semantic_role")
            else:
                control.semantic_role = None
                control.semantic_role_status = UNKNOWN

    @staticmethod
    def _is_nav_link(page: Dict[str, Any], control: UnifiedControl) -> bool:
        nav_links = page.get("nav_links") or []
        if not isinstance(nav_links, list):
            return False
        label = normalize_text(control.label)
        href = str(control.href or "")
        for link in nav_links:
            if not isinstance(link, dict):
                continue
            if label and normalize_text(link.get("text")) == label:
                return True
            link_href = str(link.get("href") or "")
            if link_href and href.endswith(link_href):
                return True
        return False

    def _page_api_paths(self, page: Dict[str, Any]) -> List[str]:
        paths: List[str] = []
        for activity in (page.get("network_activity") or []):
            if not isinstance(activity, dict) or not activity.get("is_api_candidate"):
                continue
            try:
                paths.append(urlparse(str(activity.get("url") or "")).path)
            except Exception:
                continue
        return [p for p in paths if p]

    # -- forms --------------------------------------------------------------

    def _fuse_page_forms(
        self,
        page: Dict[str, Any],
        page_id: str,
        unified_page: UnifiedPage,
        state: _State,
    ) -> None:
        dom = page.get("dom") or {}
        dom_forms = dom.get("forms") if isinstance(dom, dict) else None
        source_kind = "dom"
        if not dom_forms:
            dom_forms = page.get("forms") or []
            source_kind = "crawl"
        if not isinstance(dom_forms, list):
            return

        page_controls = [c for c in state.model.controls if c.page_id == page_id]
        button_controls = [c for c in page_controls if c.type == "button"]

        for f_index, raw_form in enumerate(dom_forms):
            if not isinstance(raw_form, dict):
                continue
            if state.form_seq >= self.limits.max_forms_total:
                state.warnings.append(
                    f"Form limit ({self.limits.max_forms_total}) reached; some forms were not fused."
                )
                break

            form_id = self._next_form_id(state)
            form_ref = (
                evidence_ref("dom", page_id, f"form_{f_index:03d}")
                if source_kind == "dom" else
                evidence_ref("crawl", page_id, f"form_{f_index:03d}")
            )
            unified_form = UnifiedForm(
                id=form_id,
                page_id=page_id,
                name=(raw_form.get("name") or raw_form.get("id") or None),
                action=(raw_form.get("action") or None),
                method=str(raw_form.get("method") or "get").upper(),
                observation_status=OBSERVED,
                dom_ref=form_ref,
                evidence_refs=[form_ref, evidence_ref("crawl", page_id)],
                evidence_sources=[source_kind, "crawl"] if source_kind != "crawl" else ["crawl"],
            )

            has_password = False
            has_search = False
            field_controls: List[UnifiedControl] = []

            for i_index, raw_input in enumerate(raw_form.get("inputs") or []):
                if not isinstance(raw_input, dict):
                    continue
                input_type = str(raw_input.get("type") or "text").lower()
                if input_type == "password":
                    has_password = True
                if input_type == "search":
                    has_search = True

                control = self._find_control_for_input(page_controls, raw_input)
                if control is None:
                    if state.control_seq >= self.limits.max_controls_total:
                        continue
                    input_ref = f"{form_ref}:input_{i_index:03d}"
                    control = UnifiedControl(
                        id=self._next_control_id(state),
                        type=dom_control_type({
                            "tag": raw_input.get("tag") or "input",
                            "type": input_type,
                        }),
                        label=(
                            raw_input.get("aria_label")
                            or raw_input.get("placeholder")
                            or raw_input.get("name")
                            or raw_input.get("id")
                            or None
                        ),
                        observation_status=OBSERVED,
                        interactable=(not bool(raw_input.get("disabled"))),
                        page_id=page_id,
                        dom_ref=input_ref,
                        dom_id=(raw_input.get("id") or None),
                        dom_name=(raw_input.get("name") or None),
                        dom_tag=(raw_input.get("tag") or "input"),
                        dom_type=input_type,
                        evidence_refs=[input_ref, evidence_ref("crawl", page_id)],
                        evidence_sources=["dom", "crawl"],
                    )
                    state.model.controls.append(control)
                    state.page_controls.setdefault(page_id, []).append(control.id)
                    unified_page.controls.append(control.id)
                    page_controls.append(control)
                    self._add_relationship(
                        state, page_id, control.id, "contains", OBSERVED,
                        evidence_refs=[input_ref],
                    )

                control.form_id = form_id
                if control.id not in unified_form.fields:
                    unified_form.fields.append(control.id)
                field_controls.append(control)
                self._add_relationship(
                    state, form_id, control.id, "contains", OBSERVED,
                    evidence_refs=[form_ref],
                )
                self._add_relationship(
                    state, control.id, form_id, "belongs_to", OBSERVED,
                    evidence_refs=[form_ref],
                )

            # Submit control
            submit_control, submit_status, submit_reason = self._resolve_submit_control(
                field_controls, button_controls, len(dom_forms)
            )
            if submit_control is not None:
                unified_form.submit_control = submit_control.id
                submit_control.form_id = submit_control.form_id or form_id
                # A submit *input* is already a field of the form and has its
                # membership relationship; only a button discovered outside the
                # form's input list needs one.
                if submit_control.id not in unified_form.fields:
                    self._add_relationship(
                        state, submit_control.id, form_id, "belongs_to", submit_status,
                        evidence_refs=[form_ref],
                        inference_reason=submit_reason,
                    )

            # Semantic role (conservative)
            if has_password:
                unified_form.semantic_role = "authentication"
                unified_form.semantic_role_status = INFERRED
                unified_form.observation_status = INFERRED
                unified_form.inference_reason = (
                    "Form contains an observed input of type=password."
                )
            elif has_search or (
                field_controls and all(c.semantic_role == "search_input" for c in field_controls)
            ):
                unified_form.semantic_role = "search"
                unified_form.semantic_role_status = INFERRED
                unified_form.observation_status = INFERRED
                unified_form.inference_reason = "Form contains an observed search input."
            else:
                unified_form.semantic_role = None
                unified_form.semantic_role_status = UNKNOWN

            state.model.forms.append(unified_form)
            unified_page.forms.append(form_id)
            self._add_relationship(
                state, page_id, form_id, "contains", OBSERVED, evidence_refs=[form_ref],
            )
            self._add_relationship(
                state, form_id, page_id, "rendered_on", OBSERVED, evidence_refs=[form_ref],
            )

    @staticmethod
    def _find_control_for_input(
        page_controls: List[UnifiedControl],
        raw_input: Dict[str, Any],
    ) -> Optional[UnifiedControl]:
        """Match a form input description to an already-built control."""
        input_id = (raw_input.get("id") or "").strip()
        input_name = (raw_input.get("name") or "").strip()
        input_type = str(raw_input.get("type") or "").lower()

        if input_id:
            for control in page_controls:
                if (control.dom_id or "") == input_id:
                    return control
        if input_name:
            for control in page_controls:
                if (control.dom_name or "") == input_name and (
                    not input_type or (control.dom_type or "").lower() == input_type
                ):
                    return control
        return None

    @staticmethod
    def _resolve_submit_control(
        field_controls: List[UnifiedControl],
        button_controls: List[UnifiedControl],
        form_count: int,
    ) -> Tuple[Optional[UnifiedControl], str, Optional[str]]:
        """
        Find the form's submit control.

        ``observed`` only when an ``input[type=submit]`` / ``button[type=submit]``
        belongs to the form; otherwise a single unambiguous button on a
        single-form page may be associated as ``inferred``. Anything less
        certain returns ``None`` rather than guessing.
        """
        for control in field_controls:
            if (control.dom_type or "").lower() in ("submit", "image"):
                return control, OBSERVED, None
        for control in button_controls:
            if (control.dom_type or "").lower() == "submit":
                return control, OBSERVED, None

        if form_count == 1 and button_controls:
            labelled = [
                c for c in button_controls
                if set(tokenize(c.label or "")) & (_SUBMIT_LABEL_WORDS | _AUTH_LABEL_WORDS | _SEARCH_WORDS)
            ]
            if len(labelled) == 1:
                return labelled[0], INFERRED, (
                    "Only form on the page and exactly one button whose label matches a "
                    "submit-style action; association is inferred, not observed."
                )
            if len(button_controls) == 1:
                return button_controls[0], INFERRED, (
                    "Only form on the page and exactly one button control present; "
                    "association is inferred, not observed."
                )
        return None, UNKNOWN, None

    # ------------------------------------------------------------------
    # 4. API endpoints
    # ------------------------------------------------------------------

    def _fuse_api_endpoints(self, ctx: Dict[str, Any], state: _State) -> None:
        """
        Normalize observed network activity (Phase 1.5C) into unified endpoints.

        SECURITY: request/response *headers*, cookies, tokens and bodies are
        never copied here — only method, host, path, status codes, content type
        and size/attempt counters.
        """
        endpoint_index: Dict[Tuple[str, str, str], UnifiedAPIEndpoint] = {}

        for page_id, page in state.raw_pages.items():
            activities = page.get("network_activity") or []
            if not isinstance(activities, list):
                continue
            unified_page = state.model.page_by_id(page_id)
            for a_index, activity in enumerate(activities):
                if not isinstance(activity, dict) or not activity.get("is_api_candidate"):
                    continue
                url = str(activity.get("url") or "")
                method = str(activity.get("method") or "GET").upper()
                try:
                    parsed = urlparse(url)
                    host, path = parsed.netloc, (parsed.path or "/")
                except Exception:
                    host, path = "", url
                key = (method, host, path)

                endpoint = endpoint_index.get(key)
                if endpoint is None:
                    if len(endpoint_index) >= self.limits.max_api_endpoints:
                        state.bump("api_endpoints_dropped")
                        continue
                    endpoint = UnifiedAPIEndpoint(
                        id=self._next_api_id(state),
                        method=method,
                        url=url,
                        path=path,
                        host=host,
                        observation_status=OBSERVED,
                        request_metadata={
                            "resource_type": activity.get("resource_type"),
                            "has_post_data": bool(activity.get("has_post_data")),
                            "post_data_size": activity.get("post_data_size") or 0,
                            "note": "Headers, cookies, tokens and bodies are intentionally excluded.",
                        },
                        response_metadata={
                            "statuses": [],
                            "content_types": [],
                        },
                        evidence_sources=["network"],
                    )
                    endpoint_index[key] = endpoint
                    state.model.api_endpoints.append(endpoint)

                endpoint.observation_count += 1
                if activity.get("request_failed"):
                    endpoint.failure_count += 1
                response = activity.get("response") or {}
                if isinstance(response, dict):
                    status = response.get("status")
                    if status is not None and status not in endpoint.response_metadata["statuses"]:
                        endpoint.response_metadata["statuses"].append(status)
                    ctype = (response.get("content_type") or "").split(";")[0].strip()
                    if ctype and ctype not in endpoint.response_metadata["content_types"]:
                        endpoint.response_metadata["content_types"].append(ctype)
                if activity.get("has_post_data"):
                    endpoint.request_metadata["has_post_data"] = True

                if page_id not in endpoint.observed_on_pages:
                    endpoint.observed_on_pages.append(page_id)
                    self._add_relationship(
                        state, endpoint.id, page_id, "observed_with", OBSERVED,
                        evidence_refs=[evidence_ref("network", page_id, f"req_{a_index:03d}")],
                    )
                if unified_page is not None and endpoint.id not in unified_page.api_endpoints:
                    unified_page.api_endpoints.append(endpoint.id)
                    if "network" not in unified_page.evidence_sources:
                        unified_page.evidence_sources.append("network")

                if len(endpoint.evidence_refs) < self.limits.max_evidence_refs_per_entity:
                    endpoint.evidence_refs.append(
                        evidence_ref("network", page_id, f"req_{a_index:03d}")
                    )

    # ------------------------------------------------------------------
    # 5. UI <-> API relationships
    # ------------------------------------------------------------------

    def _link_forms_and_controls_to_apis(self, state: _State) -> None:
        """
        Associate forms / controls with observed endpoints only where the
        evidence supports it. Co-occurrence on a page is never sufficient.
        """
        if not state.model.api_endpoints:
            return

        endpoints_by_page: Dict[str, List[UnifiedAPIEndpoint]] = {}
        for endpoint in state.model.api_endpoints:
            for page_id in endpoint.observed_on_pages:
                endpoints_by_page.setdefault(page_id, []).append(endpoint)

        for form in state.model.forms:
            page = state.raw_pages.get(form.page_id) or {}
            page_url = str(page.get("url") or "")
            candidates = endpoints_by_page.get(form.page_id, [])
            if not candidates:
                continue

            action_path = self._resolve_action_path(page_url, form.action)
            for endpoint in candidates:
                signals = {
                    "form_action_path_match": bool(
                        action_path and self._paths_equal(action_path, endpoint.path)
                    ),
                    "http_method_match": bool(
                        form.method and endpoint.method
                        and form.method.upper() == endpoint.method.upper()
                    ),
                    "endpoint_observed_on_same_page": True,
                    "label_path_keyword_overlap": self._role_path_overlap(
                        form.semantic_role, None, endpoint.path
                    ),
                }
                conf, basis = ui_api_confidence(signals)
                if conf is None:
                    continue

                if endpoint.id not in form.observed_api_endpoints:
                    form.observed_api_endpoints.append(endpoint.id)
                matched = [k for k, v in signals.items() if v]
                self._add_relationship(
                    state, form.id, endpoint.id, "submits_to", INFERRED,
                    evidence_refs=(form.evidence_refs[:2] + endpoint.evidence_refs[:2]),
                    confidence=conf, confidence_basis=basis,
                    inference_reason=(
                        "Form associated with an observed endpoint on matching signals: "
                        + ", ".join(sorted(matched))
                        + ". The submission itself was not executed during the crawl."
                    ),
                )
                if form.submit_control:
                    self._add_relationship(
                        state, form.submit_control, endpoint.id, "likely_triggers", INFERRED,
                        evidence_refs=(form.evidence_refs[:1] + endpoint.evidence_refs[:2]),
                        confidence=conf, confidence_basis=basis,
                        inference_reason=(
                            "Submit control of a form associated with this observed endpoint. "
                            "No click was performed during the crawl."
                        ),
                    )

        # Action controls with a submit-style role but no form-level link.
        linked_controls = {
            r.source_id for r in state.model.relationships if r.relationship == "likely_triggers"
        }
        for control in state.model.controls:
            if control.id in linked_controls:
                continue
            # Only controls that *perform* an action may be said to trigger a
            # request. A username field participates in a login, but it does not
            # trigger the call, so it never receives ``likely_triggers``.
            if control.semantic_role not in _ACTION_SEMANTIC_ROLES:
                continue
            for endpoint in endpoints_by_page.get(control.page_id, []):
                signals = {
                    "form_action_path_match": False,
                    "http_method_match": False,
                    "endpoint_observed_on_same_page": True,
                    "label_path_keyword_overlap": self._role_path_overlap(
                        control.semantic_role, control.label, endpoint.path
                    ),
                }
                conf, basis = ui_api_confidence(signals)
                if conf is None:
                    continue
                self._add_relationship(
                    state, control.id, endpoint.id, "likely_triggers", INFERRED,
                    evidence_refs=(control.evidence_refs[:2] + endpoint.evidence_refs[:2]),
                    confidence=conf, confidence_basis=basis,
                    inference_reason=(
                        f"Control label/semantic role ('{control.semantic_role}') overlaps with the "
                        f"observed endpoint path '{endpoint.path}' on the same page. "
                        "The interaction was not executed during the crawl."
                    ),
                )

    @staticmethod
    def _resolve_action_path(page_url: str, action: Optional[str]) -> Optional[str]:
        if action is None:
            return None
        action = str(action).strip()
        if not action:
            return None
        try:
            if page_url:
                return urlparse(urljoin(page_url, action)).path or None
            return urlparse(action).path or None
        except Exception:
            return None

    @staticmethod
    def _paths_equal(a: Optional[str], b: Optional[str]) -> bool:
        if not a or not b:
            return False
        return a.rstrip("/").lower() == b.rstrip("/").lower()

    @staticmethod
    def _role_path_overlap(
        semantic_role: Optional[str],
        label: Optional[str],
        path: Optional[str],
    ) -> bool:
        """
        True when the control's meaning demonstrably overlaps the endpoint path.

        Uses literal token overlap plus a tiny, explicit synonym set for
        authentication and search — no free-form semantic guessing.
        """
        path_tokens = set(_path_tokens(path or ""))
        if not path_tokens:
            return False
        role = (semantic_role or "").lower()
        if role.startswith("authentication"):
            if path_tokens & _AUTH_PATH_WORDS:
                return True
        if role.startswith("search"):
            if path_tokens & _SEARCH_WORDS:
                return True
        label_tokens = {t for t in tokenize(label or "") if len(t) >= _MIN_TOKEN_LEN}
        return bool(label_tokens & path_tokens)

    # ------------------------------------------------------------------
    # 6. Navigation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Lightweight normalization used only for matching graph nodes to pages."""
        if not url:
            return ""
        value = str(url).strip()
        try:
            parsed = urlparse(value)
            scheme = (parsed.scheme or "").lower()
            netloc = (parsed.netloc or "").lower()
            path = (parsed.path or "").rstrip("/")
            if not scheme and not netloc:
                return value.rstrip("/").lower()
            return f"{scheme}://{netloc}{path}".lower()
        except Exception:
            return value.rstrip("/").lower()

    def _fuse_navigation(self, ctx: Dict[str, Any], state: _State) -> None:
        """
        Convert the existing Phase 1.5A navigation graph into unified page
        relationships. The original graph is referenced, never replaced.
        """
        for page in state.model.pages:
            for key in {page.url, page.normalized_url, self._normalize_url(page.url)}:
                if key:
                    state.url_to_page.setdefault(key, page.id)
                    state.url_to_page.setdefault(key.rstrip("/"), page.id)

        graph = ctx.get("navigation_graph") or {}
        edges = graph.get("edges") if isinstance(graph, dict) else None
        if not isinstance(edges, list):
            return

        seen: set = set()
        unresolved = 0
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = self._lookup_page(state, edge.get("from"))
            target = self._lookup_page(state, edge.get("to"))
            if not source or not target or source == target:
                if not source or not target:
                    unresolved += 1
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            self._add_relationship(
                state, source, target, "navigates_to", OBSERVED,
                evidence_refs=[evidence_ref("crawl", source), evidence_ref("crawl", target)],
                inference_reason=None,
            )
            state.bump("navigation_relationships")

        if unresolved:
            state.warnings.append(
                f"{unresolved} navigation edge(s) referenced URLs that were not crawled as pages; "
                "they were left out of the unified model rather than creating placeholder pages."
            )

    def _lookup_page(self, state: _State, url: Any) -> Optional[str]:
        if not url:
            return None
        raw = str(url)
        for key in (raw, raw.rstrip("/"), self._normalize_url(raw)):
            page_id = state.url_to_page.get(key)
            if page_id:
                return page_id
        return None

    # ------------------------------------------------------------------
    # 7. User flows
    # ------------------------------------------------------------------

    def _fuse_user_flows(self, ctx: Dict[str, Any], state: _State) -> None:
        # (a) Flows reconstructed from fused forms.
        for form in state.model.forms:
            if not form.semantic_role:
                continue
            if len(state.model.user_flows) >= self.limits.max_user_flows:
                break
            page = state.model.page_by_id(form.page_id)
            steps: List[UserFlowStep] = []
            order = 1

            steps.append(UserFlowStep(
                order=order,
                action="navigate",
                description=f"Navigate to {page.url if page else form.page_id}",
                page_id=form.page_id,
                observation_status=OBSERVED,
                evidence_refs=[evidence_ref("crawl", form.page_id)],
            ))
            order += 1

            for control_id in form.fields:
                control = state.model.control_by_id(control_id)
                if control is None or control.type not in ("input", "textarea", "select", "dropdown"):
                    continue
                steps.append(UserFlowStep(
                    order=order,
                    action="input",
                    description=f"Provide a value for '{control.label or control.dom_name or control_id}'",
                    page_id=form.page_id,
                    control_id=control_id,
                    observation_status=INFERRED,
                    inference_reason=(
                        "Field observed in the form; the crawler did not enter any value."
                    ),
                    evidence_refs=control.evidence_refs[:2],
                ))
                order += 1

            if form.submit_control:
                submit = state.model.control_by_id(form.submit_control)
                steps.append(UserFlowStep(
                    order=order,
                    action="click",
                    description=f"Activate '{(submit.label if submit else None) or form.submit_control}'",
                    page_id=form.page_id,
                    control_id=form.submit_control,
                    observation_status=INFERRED,
                    inference_reason="Submit control identified by fusion; no click was performed.",
                    evidence_refs=(submit.evidence_refs[:2] if submit else []),
                ))
                order += 1

            for api_id in form.observed_api_endpoints:
                endpoint = next((e for e in state.model.api_endpoints if e.id == api_id), None)
                if endpoint is None:
                    continue
                steps.append(UserFlowStep(
                    order=order,
                    action="api_call",
                    description=f"{endpoint.method} {endpoint.path}",
                    page_id=form.page_id,
                    api_endpoint_id=api_id,
                    observation_status=INFERRED,
                    inference_reason=(
                        "Endpoint was observed on this page and matches the form action; "
                        "the causal link to the submission is inferred."
                    ),
                    evidence_refs=endpoint.evidence_refs[:2],
                ))
                order += 1

            observed_steps = sum(1 for s in steps if s.observation_status == OBSERVED)
            conf, basis = flow_confidence(observed_steps, len(steps))
            flow = UnifiedUserFlow(
                id=self._next_flow_id(state),
                name=(
                    f"{form.semantic_role.replace('_', ' ').title()} "
                    f"({page.title or page.url if page else form.page_id})"
                ).strip(),
                source="form_fusion",
                steps=steps,
                page_ids=[form.page_id],
                control_ids=[c for c in ([*form.fields, form.submit_control]) if c],
                api_endpoint_ids=list(form.observed_api_endpoints),
                semantic_role=form.semantic_role,
                observation_status=INFERRED,
                inference_reason=(
                    "Flow reconstructed from observed page, form and endpoint evidence. "
                    "Interaction steps were not executed during the crawl."
                ),
                confidence=conf,
                confidence_basis=basis,
                evidence_refs=form.evidence_refs[:3],
                evidence_sources=list(dict.fromkeys(form.evidence_sources + ["dom"])),
            )
            state.model.user_flows.append(flow)
            self._add_relationship(
                state, flow.id, form.id, "associated_with", INFERRED,
                evidence_refs=form.evidence_refs[:2],
                inference_reason="Flow derived from this form.",
            )

        # (b) Flows named by requirement analysis (no fabricated steps).
        for flow_index, raw_flow in enumerate(ctx.get("user_flows") or []):
            if len(state.model.user_flows) >= self.limits.max_user_flows:
                break
            if isinstance(raw_flow, dict):
                name = str(raw_flow.get("name") or raw_flow.get("flow") or "").strip()
            else:
                name = str(raw_flow).strip()
            if not name:
                continue
            if any(normalize_text(f.name) == normalize_text(name) for f in state.model.user_flows):
                continue
            page_ids = self._pages_matching_tokens(state, _significant_tokens(name))
            flow_ref = evidence_ref("context", "user_flows", str(flow_index))
            flow = UnifiedUserFlow(
                id=self._next_flow_id(state),
                name=name,
                source="requirement_analysis",
                steps=[],
                page_ids=page_ids,
                semantic_role=None,
                observation_status=INFERRED if page_ids else UNKNOWN,
                inference_reason=(
                    "Flow named by requirement analysis; pages associated by deterministic "
                    "name matching. No interaction steps were observed."
                    if page_ids else
                    "Flow named by requirement analysis; no crawled page could be associated, "
                    "so no steps are asserted."
                ),
                confidence=None,
                evidence_refs=(
                    [flow_ref]
                    + [evidence_ref("requirement", r.id) for r in state.model.requirements[:2]]
                ),
                evidence_sources=["requirements"],
            )
            state.model.user_flows.append(flow)

    def _pages_matching_tokens(self, state: _State, tokens: List[str]) -> List[str]:
        if not tokens:
            return []
        matches: List[str] = []
        for page in state.model.pages:
            haystack = _significant_tokens(page.title, page.url, page.page_type)
            if set(tokens) & set(haystack):
                matches.append(page.id)
        return matches

    # ------------------------------------------------------------------
    # 8. Modules / features
    # ------------------------------------------------------------------

    def _fuse_modules(self, ctx: Dict[str, Any], state: _State) -> None:
        """
        Build modules only from names that the evidence already produced
        (crawl-detected flows, requirement/feature analysis, repository
        analysis). The fusion layer never promotes "Login page" into a grander
        invented module name.
        """
        named: List[Tuple[str, str, str]] = []  # (name, source, evidence_ref)

        for index, value in enumerate(ctx.get("modules") or []):
            ref = evidence_ref("context", "modules", str(index))
            if isinstance(value, str) and value.strip():
                named.append((value.strip(), "crawl", ref))
            elif isinstance(value, dict) and value.get("name"):
                named.append((str(value["name"]).strip(), str(value.get("source") or "crawl"), ref))

        for index, value in enumerate(ctx.get("features") or []):
            ref = evidence_ref("context", "features", str(index))
            if isinstance(value, dict) and value.get("name"):
                named.append((str(value["name"]).strip(), str(value.get("source") or "features"), ref))
            elif isinstance(value, str) and value.strip():
                named.append((value.strip(), "features", ref))

        repo_data = ctx.get("repository_data") or {}
        analysis = repo_data.get("analysis") if isinstance(repo_data, dict) else {}
        if isinstance(analysis, dict):
            for index, value in enumerate(analysis.get("modules") or []):
                ref = evidence_ref("context", "repository_modules", str(index))
                if isinstance(value, str) and value.strip():
                    named.append((value.strip(), "repository", ref))
                elif isinstance(value, dict) and value.get("name"):
                    named.append((str(value["name"]).strip(), "repository", ref))

        seen: set = set()
        for name, source, source_ref in named:
            key = normalize_text(name)
            if not key or key in seen:
                continue
            seen.add(key)
            if len(state.model.modules) >= self.limits.max_modules:
                state.warnings.append(
                    f"Module limit ({self.limits.max_modules}) reached; some names were skipped."
                )
                break

            tokens = _significant_tokens(name)
            module = UnifiedModule(
                id=self._next_module_id(state),
                name=name,
                source=source,
                observation_status=INFERRED,
                inference_reason=(
                    f"Module name taken verbatim from {source} evidence ({source_ref}); pages, "
                    "controls, forms and endpoints associated by deterministic token matching."
                ),
                evidence_refs=[source_ref],
                evidence_sources=[source],
            )

            for page in state.model.pages:
                if tokens and set(tokens) & set(_significant_tokens(page.title, page.url, page.page_type)):
                    module.pages.append(page.id)
                    module.evidence_refs.append(evidence_ref("crawl", page.id))
            for control in state.model.controls:
                if tokens and set(tokens) & set(_significant_tokens(control.label, control.semantic_role)):
                    module.controls.append(control.id)
            for form in state.model.forms:
                if form.page_id in module.pages or (
                    tokens and set(tokens) & set(_significant_tokens(form.name, form.semantic_role))
                ):
                    module.forms.append(form.id)
            for endpoint in state.model.api_endpoints:
                if tokens and set(tokens) & set(_path_tokens(endpoint.path)):
                    module.api_endpoints.append(endpoint.id)

            module.evidence_refs = module.evidence_refs[: self.limits.max_evidence_refs_per_entity]
            state.model.modules.append(module)

            for page_id in module.pages:
                self._add_relationship(
                    state, page_id, module.id, "belongs_to", INFERRED,
                    evidence_refs=[evidence_ref("crawl", page_id)],
                    inference_reason=f"Page name/path tokens match module '{name}'.",
                )

    # ------------------------------------------------------------------
    # 9. Traceability
    # ------------------------------------------------------------------

    def _apply_requirement_traceability(self, state: _State) -> None:
        """
        Link entities back to requirements by deterministic keyword overlap.
        Requirement ids are never invented — only ids created in
        ``_fuse_requirements`` are referenced.
        """
        if not state.model.requirements:
            return
        for requirement in state.model.requirements:
            keywords = set(requirement.keywords)
            if not keywords:
                continue

            for module in state.model.modules:
                if keywords & set(_significant_tokens(module.name)):
                    self._attach_requirement(state, module, requirement, "satisfies",
                                             f"Module name shares keywords with {requirement.id}.")
            for page in state.model.pages:
                if keywords & set(_significant_tokens(page.title, page.url, page.page_type)):
                    self._attach_requirement(state, page, requirement, "satisfies",
                                             f"Page title/path shares keywords with {requirement.id}.")
            for control in state.model.controls:
                if keywords & set(_significant_tokens(control.label, control.semantic_role)):
                    self._attach_requirement(state, control, requirement, "satisfies",
                                             f"Control label/role shares keywords with {requirement.id}.")
            for form in state.model.forms:
                if keywords & set(_significant_tokens(form.name, form.semantic_role, form.action)):
                    self._attach_requirement(state, form, requirement, "satisfies",
                                             f"Form shares keywords with {requirement.id}.")
            for flow in state.model.user_flows:
                if keywords & set(_significant_tokens(flow.name)):
                    if requirement.id not in flow.requirement_refs:
                        flow.requirement_refs.append(requirement.id)
                    self._add_relationship(
                        state, flow.id, requirement.id, "satisfies", INFERRED,
                        evidence_refs=[evidence_ref("requirement", requirement.id)],
                        inference_reason=f"Flow name shares keywords with {requirement.id}.",
                    )
            for endpoint in state.model.api_endpoints:
                if keywords & set(_path_tokens(endpoint.path)):
                    self._attach_requirement(state, endpoint, requirement, "satisfies",
                                             f"Endpoint path shares keywords with {requirement.id}.")

    def _attach_requirement(self, state: _State, entity: Any, requirement: UnifiedRequirement,
                            relationship: str, reason: str) -> None:
        refs = getattr(entity, "requirement_refs", None)
        if refs is None:
            return
        if requirement.id not in refs:
            refs.append(requirement.id)
        self._add_relationship(
            state, entity.id, requirement.id, relationship, INFERRED,
            evidence_refs=[evidence_ref("requirement", requirement.id)],
            inference_reason=reason,
        )

    def _apply_repository_traceability(self, state: _State) -> None:
        """
        Associate unified entities with repository sources that the repository
        analysis actually returned. File paths are used verbatim; the ``symbol``
        is the file stem and is explicitly marked as derived.
        """
        if not state.repository_sources:
            return
        for source in state.repository_sources:
            tokens = set(source.get("tokens") or [])
            if not tokens:
                continue
            for page in state.model.pages:
                if tokens & set(_significant_tokens(page.title, page.url, page.page_type)):
                    self._attach_repository(page, source, "filename matches page title/path")
            for module in state.model.modules:
                if tokens & set(_significant_tokens(module.name)):
                    self._attach_repository(module, source, "filename matches module name")
            for control in state.model.controls:
                if tokens & set(_significant_tokens(control.label)):
                    self._attach_repository(control, source, "filename matches control label")

    @staticmethod
    def _attach_repository(entity: Any, source: Dict[str, Any], match_reason: str) -> None:
        refs = getattr(entity, "repository_refs", None)
        if refs is None:
            return
        if any(r.get("file") == source["file"] for r in refs):
            return
        refs.append({
            "file": source["file"],
            "symbol": source["symbol"],
            "symbol_status": INFERRED,
            "match_reason": match_reason,
            "evidence_ref": source["evidence_ref"],
        })
        evidence = getattr(entity, "evidence_refs", None)
        if isinstance(evidence, list) and source["evidence_ref"] not in evidence:
            evidence.append(source["evidence_ref"])

    # ------------------------------------------------------------------
    # 10. Application summary, evidence summary, metadata
    # ------------------------------------------------------------------

    def _build_application(self, ctx: Dict[str, Any], state: _State) -> None:
        state.model.application = {
            "name": ctx.get("app_name") or None,
            "url": ctx.get("url") or None,
            "app_type": ctx.get("app_type") or None,
            "framework": ctx.get("framework") or None,
            "technology_stack": ctx.get("technology_stack") or {},
            "module_name": ctx.get("module_name") or None,
            "repo_url": ctx.get("repo_url") or None,
            "page_count": len(state.model.pages),
            "observation_status": OBSERVED if state.model.pages else UNKNOWN,
            "evidence_refs": [evidence_ref("crawl", p.id) for p in state.model.pages[:5]],
        }

    def _entity_status_counts(self, state: _State) -> Dict[str, int]:
        counts = {OBSERVED: 0, INFERRED: 0, UNKNOWN: 0}
        collections = (
            state.model.pages, state.model.controls, state.model.forms,
            state.model.api_endpoints, state.model.user_flows,
            state.model.modules, state.model.requirements,
        )
        for collection in collections:
            for item in collection:
                status = getattr(item, "observation_status", UNKNOWN)
                if status in counts:
                    counts[status] += 1
                else:
                    counts[UNKNOWN] += 1
        for rel in state.model.relationships:
            if rel.observation_status in counts:
                counts[rel.observation_status] += 1
            else:
                counts[UNKNOWN] += 1
        return counts

    def _build_evidence_summary(self, ctx: Dict[str, Any], state: _State) -> None:
        pages = ctx.get("pages") or []
        status_counts = self._entity_status_counts(state)

        def _count_pages(predicate) -> int:
            total = 0
            for page in pages:
                page = page if isinstance(page, dict) else {}
                try:
                    if predicate(page):
                        total += 1
                except Exception:
                    continue
            return total

        state.model.evidence_summary = {
            "requirements": len(state.model.requirements),
            "repository_sources": len(state.repository_sources),
            "pages": len(state.model.pages),
            "dom_controls": state.stats.get("dom_controls", 0),
            "accessibility_nodes": state.stats.get("accessibility_nodes", 0),
            "visual_elements": state.stats.get("visual_elements", 0),
            "controls": len(state.model.controls),
            "forms": len(state.model.forms),
            "api_endpoints": len(state.model.api_endpoints),
            "user_flows": len(state.model.user_flows),
            "modules": len(state.model.modules),
            "relationships": len(state.model.relationships),
            "observed_entities": status_counts[OBSERVED],
            "inferred_entities": status_counts[INFERRED],
            "unknown_entities": status_counts[UNKNOWN],
            "coverage": {
                "pages_with_dom": _count_pages(lambda p: bool(p.get("dom"))),
                "pages_with_accessibility": _count_pages(lambda p: bool(p.get("accessibility_tree"))),
                "pages_with_network": _count_pages(lambda p: bool(p.get("network_activity"))),
                "pages_with_screenshot": _count_pages(
                    lambda p: (p.get("screenshot") or {}).get("status") == "success"
                ),
                "pages_with_visual_ui": _count_pages(
                    lambda p: (p.get("visual_ui") or {}).get("status") == "success"
                ),
            },
            "correlation": {
                "controls_with_accessibility": state.stats.get("controls_with_accessibility", 0),
                "controls_with_visual_correlation": state.stats.get("controls_with_visual_correlation", 0),
                "controls_with_semantic_role": state.stats.get("controls_with_semantic_role", 0),
                "visual_only_controls": state.stats.get("visual_only_controls", 0),
                "ambiguous_visual_matches": state.stats.get("ambiguous_visual_matches", 0),
                "duplicate_dom_elements_skipped": state.stats.get("duplicate_dom_elements_skipped", 0),
                "navigation_relationships": state.stats.get("navigation_relationships", 0),
            },
        }

    def _detected_sources(self, ctx: Dict[str, Any], state: _State) -> List[str]:
        """Report only the evidence sources that were actually present."""
        sources: List[str] = []
        if state.model.requirements:
            sources.append("requirements")
        if state.repository_sources or ctx.get("repository_data"):
            sources.append("repository")
        pages = ctx.get("pages") or []
        if pages:
            sources.append("crawl")
        if any(isinstance(p, dict) and p.get("dom") for p in pages):
            sources.append("dom")
        if any(isinstance(p, dict) and p.get("accessibility_tree") for p in pages):
            sources.append("accessibility")
        if any(isinstance(p, dict) and p.get("network_activity") for p in pages):
            sources.append("network")
        if any(isinstance(p, dict) and (p.get("screenshot") or {}).get("status") == "success"
               for p in pages):
            sources.append("screenshot")
        if any(isinstance(p, dict) and (p.get("visual_ui") or {}).get("status") == "success"
               for p in pages):
            sources.append("visual_ui")
        return sources
