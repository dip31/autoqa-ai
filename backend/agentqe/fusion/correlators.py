"""
Phase 1.5F — Deterministic correlators.

Everything in this module is pure, deterministic and dependency-free (stdlib
only). No LLM is involved in correlation: the basic algorithm must be
explainable and reproducible.

Three correlation problems are solved here:

1. DOM element  <-> Accessibility node   (``correlate_ax_to_dom``)
2. Visual element <-> DOM element        (``correlate_visual_to_dom``)
3. Text / geometry / role similarity primitives used by both.

Scores produced here are *internal matching scores*, NOT model confidences.
They are converted into (documented) confidence values by
``agentqe.fusion.confidence`` only where that is meaningful.
"""

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Thresholds & weights (explicit, tunable, documented)
# ---------------------------------------------------------------------------

#: Visual <-> DOM: weights applied to each available signal. If a signal is
#: unavailable (e.g. no DOM bounding box) its weight is redistributed over the
#: remaining signals so the score stays comparable to the thresholds below.
W_VISUAL_TEXT = 0.55
W_VISUAL_BBOX = 0.30
W_VISUAL_ROLE = 0.15

#: A visual element is merged into a DOM control only at/above this score.
VISUAL_DOM_MATCH_THRESHOLD = 0.62

#: If the runner-up candidate is within this margin of the best candidate the
#: match is considered AMBIGUOUS and is NOT forced — the visual element stays a
#: separate record and uncertain ``observed_with`` relationships are emitted.
VISUAL_DOM_AMBIGUITY_MARGIN = 0.08

#: Minimum IoU for two boxes to be considered "the same region" on its own.
BBOX_STRONG_OVERLAP_IOU = 0.50

#: Accessibility <-> DOM weights and threshold.
W_AX_NAME = 0.70
W_AX_ROLE = 0.30
AX_DOM_MATCH_THRESHOLD = 0.70

#: Bounded traversal limits (performance guard rails).
MAX_AX_NODES = 2000
MAX_VISUAL_ELEMENTS = 500
MAX_DOM_ELEMENTS = 500

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
_SPLIT_RE = re.compile(r"[^a-z0-9]+")

_STOPWORDS = {
    "a", "an", "the", "to", "of", "and", "or", "in", "on", "for", "with",
    "your", "my", "is", "are", "be", "please", "click", "here", "this", "that",
}


# ---------------------------------------------------------------------------
# Text primitives
# ---------------------------------------------------------------------------

def normalize_text(value: Optional[str]) -> str:
    """Lowercase, strip punctuation and collapse whitespace. Deterministic."""
    if not value:
        return ""
    lowered = str(value).strip().lower()
    lowered = _NON_ALNUM_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", lowered).strip()


def tokenize(value: Optional[str], drop_stopwords: bool = True) -> List[str]:
    """Split into alphanumeric tokens (optionally dropping stopwords)."""
    if not value:
        return []
    tokens = [t for t in _SPLIT_RE.split(str(value).lower()) if t]
    if drop_stopwords:
        tokens = [t for t in tokens if t not in _STOPWORDS]
    return tokens


def text_similarity(a: Optional[str], b: Optional[str]) -> float:
    """
    Deterministic 0.0–1.0 text similarity.

    Blend of:
      * token-set Jaccard   (robust to word order / extra words)
      * difflib ratio       (robust to minor spelling/spacing differences)

    Exact normalized equality always returns 1.0. Empty input returns 0.0
    (absence of text is *not* evidence of a match).
    """
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    ta, tb = set(tokenize(na)), set(tokenize(nb))
    if ta and tb:
        jaccard = len(ta & tb) / float(len(ta | tb))
    else:
        jaccard = 0.0

    ratio = difflib.SequenceMatcher(None, na, nb).ratio()

    # Containment bonus: "sign in" inside "sign in to your account".
    if na in nb or nb in na:
        ratio = max(ratio, 0.85)

    return round(max(0.0, min(1.0, 0.5 * jaccard + 0.5 * ratio)), 4)


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def dom_bbox_to_xyxy(bbox: Any) -> Optional[List[float]]:
    """
    Convert the crawler's DOM bounding box ``{x, y, width, height}`` into
    ``[x1, y1, x2, y2]``. Returns ``None`` when unusable (missing or zero area).
    """
    if not isinstance(bbox, dict):
        return None
    try:
        x = float(bbox.get("x", 0.0))
        y = float(bbox.get("y", 0.0))
        w = float(bbox.get("width", 0.0))
        h = float(bbox.get("height", 0.0))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return [x, y, x + w, y + h]


def normalize_bbox(bbox_xyxy: Optional[List[float]], width: Optional[float],
                   height: Optional[float]) -> Optional[List[float]]:
    """Normalize a pixel box to 0..1 given image dimensions. Clamped."""
    if not bbox_xyxy or not width or not height:
        return None
    try:
        w = float(width)
        h = float(height)
        if w <= 0 or h <= 0:
            return None
        x1, y1, x2, y2 = [float(v) for v in bbox_xyxy[:4]]
    except (TypeError, ValueError):
        return None
    out = [x1 / w, y1 / h, x2 / w, y2 / h]
    out = [max(0.0, min(1.0, v)) for v in out]
    if out[2] <= out[0] or out[3] <= out[1]:
        return None
    return [round(v, 6) for v in out]


def is_valid_bbox(bbox: Any, normalized: bool = False) -> bool:
    """Structural validity check used by fusion and by the validators."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return False
    if x2 <= x1 or y2 <= y1:
        return False
    if normalized:
        return all(-0.0001 <= v <= 1.0001 for v in (x1, y1, x2, y2))
    return all(v >= -1.0 for v in (x1, y1, x2, y2))


def bbox_iou(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """Intersection-over-union of two ``[x1, y1, x2, y2]`` boxes."""
    if not is_valid_bbox(a) or not is_valid_bbox(b):
        return 0.0
    ax1, ay1, ax2, ay2 = [float(v) for v in a[:4]]
    bx1, by1, bx2, by2 = [float(v) for v in b[:4]]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = ix2 - ix1, iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return round(inter / union, 4)


def bbox_center_proximity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """
    Spatial proximity of box centres in normalized space, mapped to 0..1
    (1.0 = identical centre, 0.0 = opposite corners of the image).
    """
    if not is_valid_bbox(a) or not is_valid_bbox(b):
        return 0.0
    acx = (float(a[0]) + float(a[2])) / 2.0
    acy = (float(a[1]) + float(a[3])) / 2.0
    bcx = (float(b[0]) + float(b[2])) / 2.0
    bcy = (float(b[1]) + float(b[3])) / 2.0
    dist = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
    max_dist = 2 ** 0.5
    return round(max(0.0, 1.0 - (dist / max_dist)), 4)


def bbox_overlap_score(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """
    Combined geometric agreement: IoU dominates, centre proximity contributes
    when boxes are close but differently sized (common between a YOLO region
    and the DOM node's client rect).
    """
    iou = bbox_iou(a, b)
    if iou >= BBOX_STRONG_OVERLAP_IOU:
        return iou
    prox = bbox_center_proximity(a, b)
    # Proximity alone is weak evidence — cap its contribution.
    return round(max(iou, 0.6 * prox if prox > 0.9 else 0.0), 4)


# ---------------------------------------------------------------------------
# Type / role vocabulary mapping
# ---------------------------------------------------------------------------

_INPUT_TEXTUAL_TYPES = {
    "text", "email", "password", "search", "tel", "url", "number", "date",
    "datetime-local", "month", "week", "time", "file", "color", "range",
}

#: DOM (tag, type, role) -> unified control type.
def dom_control_type(element: Dict[str, Any]) -> str:
    """
    Map a DOM element onto the allowed control-type vocabulary.

    Never guesses a specific type: unrecognised elements become ``"other"``.
    """
    tag = (element.get("tag") or "").lower()
    etype = (element.get("type") or "").lower()
    role = (element.get("role") or "").lower()

    if tag == "button" or role == "button" or etype in ("submit", "button", "reset"):
        return "button"
    if tag == "a" or role == "link":
        return "link"
    if tag == "textarea":
        return "textarea"
    if tag == "select" or role in ("combobox", "listbox"):
        return "select"
    if tag == "input":
        if etype == "checkbox":
            return "checkbox"
        if etype == "radio":
            return "radio"
        if etype in _INPUT_TEXTUAL_TYPES or etype == "":
            return "input"
        return "other"
    if role == "checkbox":
        return "checkbox"
    if role == "radio":
        return "radio"
    if role == "tab":
        return "tab"
    if role in ("menu", "menuitem", "menubar"):
        return "menu"
    if role == "textbox":
        return "input"
    return "other"


#: Visual parser type -> unified control type (identity for known values).
_VISUAL_TYPE_MAP = {
    "button": "button",
    "input": "input",
    "textbox": "input",
    "text_field": "input",
    "checkbox": "checkbox",
    "radio": "radio",
    "link": "link",
    "dropdown": "dropdown",
    "select": "select",
    "combobox": "select",
    "menu": "menu",
    "tab": "tab",
    "textarea": "textarea",
    "icon": "icon",
}


def visual_control_type(visual_type: Optional[str]) -> str:
    """Map a visual parser type onto the allowed control-type vocabulary."""
    key = (visual_type or "").strip().lower()
    return _VISUAL_TYPE_MAP.get(key, "other")


#: Types that may legitimately describe the same widget across modalities.
_TYPE_EQUIVALENCE = [
    {"button", "icon"},              # icon-only buttons
    {"input", "textarea", "other"},  # text entry regions
    {"select", "dropdown"},
    {"link", "button"},             # styled links / link-buttons
    {"checkbox", "radio"},
    {"menu", "tab"},
]


def role_compatibility(type_a: str, type_b: str) -> float:
    """
    1.0 identical, 0.6 plausibly the same widget, 0.3 when one side is unknown
    (``other``), 0.0 incompatible. Used as a weighted signal, never as a veto
    on its own.
    """
    a = (type_a or "other").lower()
    b = (type_b or "other").lower()
    if a == b:
        return 1.0
    if a == "other" or b == "other":
        return 0.3
    for group in _TYPE_EQUIVALENCE:
        if a in group and b in group:
            return 0.6
    return 0.0


# ---------------------------------------------------------------------------
# DOM helpers
# ---------------------------------------------------------------------------

def dom_element_label(element: Dict[str, Any]) -> str:
    """
    Best available human label for a DOM element, in priority order:
    aria-label, visible text, placeholder, name, id.

    Note: the crawler already blanks text/values for sensitive inputs
    (password, token, ...), so nothing sensitive can leak through here.
    """
    for key in ("aria_label", "text", "placeholder", "label_text", "name", "id"):
        value = element.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def dom_element_key(element: Dict[str, Any], index: int) -> str:
    """Deterministic identity key for a DOM element (used for de-duplication)."""
    return "|".join([
        (element.get("tag") or "").lower(),
        (element.get("id") or ""),
        (element.get("name") or ""),
        (element.get("type") or "").lower(),
        normalize_text(dom_element_label(element)),
        str(element.get("href") or ""),
    ])


# ---------------------------------------------------------------------------
# Accessibility tree helpers
# ---------------------------------------------------------------------------

def flatten_ax_tree(accessibility_tree: Any, max_nodes: int = MAX_AX_NODES) -> List[Dict[str, Any]]:
    """
    Depth-first flatten of the crawler's accessibility tree into an ordered list
    of ``{"index", "role", "name", "node"}`` records.

    ``index`` is the stable traversal position used in evidence references
    (``ax:page_001:node_014``). Both CDP and dom_fallback trees are supported.
    """
    if not isinstance(accessibility_tree, dict):
        return []
    root = accessibility_tree.get("root")
    if not isinstance(root, dict) or not root:
        return []

    out: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = [root]
    while stack and len(out) < max_nodes:
        node = stack.pop(0)
        if not isinstance(node, dict):
            continue
        out.append({
            "index": len(out),
            "role": (node.get("role") or ""),
            "name": (node.get("name") or ""),
            "node": node,
        })
        children = node.get("children") or []
        if isinstance(children, list):
            # Preserve document order.
            stack = list(children) + stack
    return out


#: ARIA role -> unified control type (only for roles we can map safely).
_AX_ROLE_TYPE = {
    "button": "button",
    "link": "link",
    "textbox": "input",
    "searchbox": "input",
    "checkbox": "checkbox",
    "radio": "radio",
    "combobox": "select",
    "listbox": "select",
    "menuitem": "menu",
    "menu": "menu",
    "tab": "tab",
    "img": "icon",
}


def ax_role_control_type(role: Optional[str]) -> str:
    return _AX_ROLE_TYPE.get((role or "").strip().lower(), "other")


def correlate_ax_to_dom(
    dom_elements: List[Dict[str, Any]],
    ax_nodes: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """
    Correlate accessibility nodes with DOM elements.

    Signals: accessible name vs DOM label (weight 0.70) and role compatibility
    (weight 0.30). A DOM element and an AX node are matched at most once
    (greedy best-first assignment, deterministic tie-breaking by index).

    Not every AX node has a DOM counterpart (text nodes, generic containers,
    synthesised roots) — unmatched nodes are simply left unmatched.

    Returns:
        ``{dom_index: {"ax_index", "score", "role", "name"}}``
    """
    if not dom_elements or not ax_nodes:
        return {}

    candidates: List[Tuple[float, int, int]] = []
    for d_idx, el in enumerate(dom_elements[:MAX_DOM_ELEMENTS]):
        d_label = dom_element_label(el)
        d_type = dom_control_type(el)
        for a in ax_nodes:
            a_idx = a["index"]
            a_role = a.get("role") or ""
            if a_role.lower() in ("", "generic", "none", "presentation", "webarea",
                                  "rootwebarea", "text", "statictext"):
                continue
            name_score = text_similarity(d_label, a.get("name"))
            role_score = role_compatibility(d_type, ax_role_control_type(a_role))
            if name_score <= 0.0 and role_score < 1.0:
                continue
            score = W_AX_NAME * name_score + W_AX_ROLE * role_score
            if score >= AX_DOM_MATCH_THRESHOLD:
                candidates.append((round(score, 4), d_idx, a_idx))

    # Deterministic ordering: score desc, then dom index asc, then ax index asc.
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    matches: Dict[int, Dict[str, Any]] = {}
    used_ax: set = set()
    ax_by_index = {a["index"]: a for a in ax_nodes}
    for score, d_idx, a_idx in candidates:
        if d_idx in matches or a_idx in used_ax:
            continue
        node = ax_by_index.get(a_idx, {})
        matches[d_idx] = {
            "ax_index": a_idx,
            "score": score,
            "role": node.get("role", ""),
            "name": node.get("name", ""),
        }
        used_ax.add(a_idx)
    return matches


# ---------------------------------------------------------------------------
# Visual <-> DOM correlation
# ---------------------------------------------------------------------------

def visual_element_text(visual: Dict[str, Any]) -> str:
    """Best available text for a visual element (OCR text, else icon caption)."""
    for key in ("text", "caption"):
        value = visual.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def score_visual_dom_pair(
    visual: Dict[str, Any],
    dom_element: Dict[str, Any],
    dom_bbox_normalized: Optional[List[float]] = None,
    bbox_reliable: bool = True,
) -> Dict[str, Any]:
    """
    Score one (visual element, DOM element) pair.

    ``correlation_score = text*w_text + bbox*w_bbox + role*w_role`` with weights
    renormalized over the signals that are actually available.

    This is an internal *matching* score. It is NOT a model confidence.
    """
    v_text = visual_element_text(visual)
    d_label = dom_element_label(dom_element)
    text_score = text_similarity(v_text, d_label)

    v_bbox = visual.get("bbox_normalized") or None
    bbox_available = bool(bbox_reliable and is_valid_bbox(v_bbox, normalized=True)
                          and is_valid_bbox(dom_bbox_normalized, normalized=True))
    bbox_score = bbox_overlap_score(v_bbox, dom_bbox_normalized) if bbox_available else 0.0

    role_score = role_compatibility(
        visual_control_type(visual.get("type")), dom_control_type(dom_element)
    )

    signals = {"text": (text_score, W_VISUAL_TEXT), "role": (role_score, W_VISUAL_ROLE)}
    if bbox_available:
        signals["bbox"] = (bbox_score, W_VISUAL_BBOX)

    total_weight = sum(w for _, w in signals.values())
    score = sum(v * w for v, w in signals.values()) / total_weight if total_weight else 0.0

    return {
        "score": round(score, 4),
        "text_similarity": text_score,
        "bbox_overlap": bbox_score,
        "bbox_used": bbox_available,
        "role_compatibility": role_score,
        "weights": {k: round(w / total_weight, 4) for k, (_, w) in signals.items()} if total_weight else {},
    }


def correlate_visual_to_dom(
    visual_elements: List[Dict[str, Any]],
    dom_elements: List[Dict[str, Any]],
    dom_bboxes_normalized: Optional[List[Optional[List[float]]]] = None,
    bbox_reliable: bool = True,
    threshold: float = VISUAL_DOM_MATCH_THRESHOLD,
    ambiguity_margin: float = VISUAL_DOM_AMBIGUITY_MARGIN,
) -> List[Dict[str, Any]]:
    """
    Correlate visual UI elements with DOM elements on the same page.

    Returns one record per visual element::

        {
          "visual_index": int,
          "dom_index": int | None,      # None when no confident match
          "score": float,
          "ambiguous": bool,
          "signals": {...},             # why this score
          "candidates": [ {dom_index, score}, ... ]   # top runners-up
        }

    Ambiguity policy: when the best and second-best candidates are within
    ``ambiguity_margin`` the match is NOT forced — ``dom_index`` is ``None`` and
    ``ambiguous`` is ``True``, so the caller can record an uncertain
    relationship instead of silently merging the wrong pair.

    A DOM element is claimed by at most one visual element (best score wins).
    """
    results: List[Dict[str, Any]] = []
    if not visual_elements:
        return results

    dom_bboxes = dom_bboxes_normalized or [None] * len(dom_elements)

    # 1. Score every pair once.
    scored: List[List[Dict[str, Any]]] = []
    for v_idx, visual in enumerate(visual_elements[:MAX_VISUAL_ELEMENTS]):
        row: List[Dict[str, Any]] = []
        for d_idx, dom_el in enumerate(dom_elements[:MAX_DOM_ELEMENTS]):
            d_bbox = dom_bboxes[d_idx] if d_idx < len(dom_bboxes) else None
            signals = score_visual_dom_pair(visual, dom_el, d_bbox, bbox_reliable)
            if signals["score"] > 0.0:
                row.append({"dom_index": d_idx, **signals})
        row.sort(key=lambda r: (-r["score"], r["dom_index"]))
        scored.append(row)

    # 2. Greedy, deterministic assignment across visual elements.
    order = sorted(
        range(len(scored)),
        key=lambda i: (-(scored[i][0]["score"] if scored[i] else 0.0), i),
    )
    claimed_dom: set = set()
    assignment: Dict[int, Dict[str, Any]] = {}

    for v_idx in order:
        row = [r for r in scored[v_idx] if r["dom_index"] not in claimed_dom]
        best = row[0] if row else None
        runner_up = row[1] if len(row) > 1 else None

        record: Dict[str, Any] = {
            "visual_index": v_idx,
            "dom_index": None,
            "score": best["score"] if best else 0.0,
            "ambiguous": False,
            "signals": {k: v for k, v in (best or {}).items() if k != "dom_index"},
            "candidates": [{"dom_index": r["dom_index"], "score": r["score"]} for r in row[:3]],
        }

        if best and best["score"] >= threshold:
            if runner_up and (best["score"] - runner_up["score"]) < ambiguity_margin:
                record["ambiguous"] = True      # do NOT force a match
            else:
                record["dom_index"] = best["dom_index"]
                claimed_dom.add(best["dom_index"])
        assignment[v_idx] = record

    for v_idx in range(len(scored)):
        results.append(assignment[v_idx])
    return results
