"""
Phase 5 — Selector Resolution Strategy.

Given a *step target* (what the test wants to interact with, e.g. "email",
"Sign In", "the checkout button") and the observed application evidence, produce
an ordered list of :class:`SelectorCandidate` locators.

Ordering follows the Phase 5 robustness ladder exactly:

    1. accessibility role/name       (get_by_role / get_by_label / get_by_text)
    2. stable test identifier        (data-testid, data-test, data-test-id)
    3. label                        (associated <label>)
    4. stable attribute             (id / name / aria-label / placeholder)
    5. observed CSS selector        (built from observed identifiers only)
    6. observed XPath               (last resort, only if evidence carries one)

Generated ``nth-child`` chains are never produced: they are not observed
evidence and are the classic source of flaky tests.
"""

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from agentqe.execution.schemas import SelectorCandidate

logger = logging.getLogger(__name__)

#: Attributes that commonly carry a stable test identifier, in preference order.
TEST_ID_ATTRIBUTES = ("data-testid", "data-test-id", "data-test", "data-qa", "data-cy")

#: Attributes used for the "stable attribute" rung, in preference order.
STABLE_ATTRIBUTES = ("id", "name", "aria-label", "placeholder", "data-testid")

#: Attributes that are too volatile to build a CSS selector from.
_VOLATILE_CLASS = re.compile(r"(^|[-_ ])(css|sc|jsx|emotion|hash|random)([-_0-9]|$)", re.I)
_CSS_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")

#: Control types (as recorded by the crawler / fusion layer) → ARIA role.
ROLE_BY_CONTROL_TYPE = {
    "button": "button",
    "submit": "button",
    "reset": "button",
    "link": "link",
    "checkbox": "checkbox",
    "radio": "radio",
    "select": "combobox",
    "combobox": "combobox",
    "textbox": "textbox",
    "text": "textbox",
    "email": "textbox",
    "password": "textbox",
    "search": "searchbox",
    "tel": "textbox",
    "url": "textbox",
    "number": "spinbutton",
    "file": "textbox",
    "input": "textbox",
    "textarea": "textbox",
    "form": "form",
    "heading": "heading",
}

#: Words that are noise when matching a step target against a control.
_STOP_WORDS = {
    "the", "a", "an", "on", "to", "of", "and", "with", "into", "in", "at",
    "button", "link", "field", "input", "box", "element", "control", "page",
    "click", "clicking", "tap", "select", "choose", "press", "check",
    "text", "value", "label", "tab", "option", "menu", "item",
}


def normalise(text: Any) -> str:
    """Lowercase, collapse whitespace, strip punctuation noise."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def tokens(text: Any) -> List[str]:
    """Meaningful lowercase tokens for fuzzy matching."""
    cleaned = normalise(text)
    cleaned = re.sub(r"[^a-z0-9\s\-_]+", " ", cleaned)
    return [t for t in cleaned.split() if t and t not in _STOP_WORDS and len(t) > 1]


def _is_stable_class(cls: str) -> bool:
    """A class is stable if it is not a build-hash / framework utility class."""
    if not cls:
        return False
    if _VOLATILE_CLASS.search(cls):
        return False
    # Random-looking: css-1x2y3z, sc-bdVaJa, _3kFg
    if re.match(r"^(css|sc|jss|emotion)-[a-z0-9]{4,}$", cls, re.I):
        return False
    if re.match(r"^[a-z]{1,3}[A-Za-z0-9]{5,}$", cls) and not re.search(r"[a-z]{3,}", cls):
        return False
    return bool(_CSS_IDENT.match(cls))


def _css_escape(value: str) -> str:
    """Quote a value for use inside a CSS attribute selector."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ── Evidence normalisation ──────────────────────────────────────────────────

def normalise_evidence_element(element: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a crawler/fusion control dict into the keys this module needs.

    Accepts both raw crawled DOM elements and :class:`UnifiedControl` dicts.
    """
    if not isinstance(element, dict):
        return {}
    control = element.get("control") if isinstance(element.get("control"), dict) else {}
    dom = element.get("dom") if isinstance(element.get("dom"), dict) else {}
    source = {**dom, **control, **{k: v for k, v in element.items() if not isinstance(v, dict)}}

    role = (
        element.get("role")
        or source.get("role")
        or element.get("semantic_role")
        or source.get("semantic_role")
        or ""
    )
    tag = element.get("dom_tag") or source.get("tag") or source.get("dom_tag") or ""
    ctype = element.get("dom_type") or source.get("type") or source.get("dom_type") or ""

    names = [
        element.get("label"),
        element.get("text"),
        source.get("label"),
        source.get("aria_label"),
        source.get("aria-label"),
        source.get("placeholder"),
        source.get("text"),
        element.get("dom_name"),
        source.get("name"),
    ]
    name = next((str(n).strip() for n in names if n and str(n).strip()), "")

    return {
        "id": str(element.get("dom_id") or source.get("id") or "").strip(),
        "name_attr": str(element.get("dom_name") or source.get("name") or "").strip(),
        "role": str(role or "").strip(),
        "tag": str(tag or "").strip().lower(),
        "type": str(ctype or "").strip().lower(),
        "label": str(element.get("label") or source.get("aria_label") or "").strip(),
        "text": str(element.get("text") or source.get("text") or "").strip(),
        "placeholder": str(source.get("placeholder") or "").strip(),
        "class": str(source.get("class") or source.get("className") or "").strip(),
        "page_id": str(element.get("page_id") or ""),
        "element_id": str(element.get("id") or ""),
        "observation_status": str(element.get("observation_status") or "observed"),
        "evidence_refs": list(element.get("evidence_refs") or []),
        "source": element,
    }


def collect_evidence_elements(
    app_context: Any,
    page_hint: str = "",
) -> List[Dict[str, Any]]:
    """
    Gather every observed interactive element from an ApplicationContext.

    Sources, in order: unified model controls → crawled page DOM elements →
    crawled page forms' inputs. Returns normalised dicts.
    """
    if app_context is None:
        return []

    elements: List[Dict[str, Any]] = []
    seen: set = set()

    def _push(raw: Dict[str, Any]) -> None:
        norm = normalise_evidence_element(raw)
        if not norm:
            return
        key = (norm.get("id"), norm.get("name_attr"), norm.get("tag"),
               norm.get("type"), norm.get("text"), norm.get("placeholder"),
               norm.get("page_id"))
        if key in seen:
            return
        seen.add(key)
        elements.append(norm)

    unified = getattr(app_context, "unified_model", None) or None
    if isinstance(unified, dict):
        page_filter = normalise(page_hint)
        for control in unified.get("controls") or []:
            if not isinstance(control, dict):
                continue
            if page_filter and normalise(control.get("page_id")) != page_filter:
                continue
            _push(control)

    for page in getattr(app_context, "pages", None) or []:
        if not isinstance(page, dict):
            continue
        if page_hint and normalise(page.get("url")) != page_hint:
            continue
        dom = page.get("dom") if isinstance(page.get("dom"), dict) else {}
        for el in dom.get("interactive_elements") or []:
            if isinstance(el, dict):
                _push({**el, "page_id": page.get("page_id") or page.get("url") or ""})
        for form in dom.get("forms") or []:
            if isinstance(form, dict):
                for inp in form.get("inputs") or []:
                    if isinstance(inp, dict):
                        _push({
                            **inp,
                            "tag": inp.get("tag") or "input",
                            "page_id": page.get("page_id") or page.get("url") or "",
                        })

    # page_data is the single-page crawl result
    page_data = getattr(app_context, "page_data", None) or {}
    dom_data = page_data.get("dom") if isinstance(page_data, dict) else {}
    for el in (dom_data or {}).get("interactive_elements") or []:
        if isinstance(el, dict):
            _push(el)

    return elements


# ── Target matching ─────────────────────────────────────────────────────────

def score_element(element: Dict[str, Any], target: str) -> float:
    """
    Deterministic 0..1 match score between a step target and an observed element.

    No LLM, no randomness — the same target always scores the same.
    """
    target_norm = normalise(target)
    if not target_norm:
        return 0.0
    target_tokens = set(tokens(target))

    best = 0.0
    for field in ("text", "label", "placeholder", "name_attr", "id"):
        value = normalise(element.get(field))
        if not value:
            continue
        if value == target_norm:
            score = 1.0
        elif target_norm in value or value in target_norm:
            score = 0.85
        else:
            field_tokens = set(tokens(value))
            if not field_tokens or not target_tokens:
                score = 0.0
            else:
                overlap = len(field_tokens & target_tokens)
                if overlap:
                    score = 0.4 + 0.4 * (overlap / max(len(target_tokens), 1))
                else:
                    score = 0.0
        if score > best:
            best = score
    return round(best, 4)


def find_target_element(
    target: str,
    elements: Sequence[Dict[str, Any]],
    min_score: float = 0.6,
) -> Optional[Dict[str, Any]]:
    """
    Best-matching observed element for ``target``.

    Ties are broken deterministically by (score desc, fewer stable attributes
    first, original order) so results are reproducible.
    """
    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx, element in enumerate(elements):
        score = score_element(element, target)
        if score >= min_score:
            specificity = 0 if (element.get("id") or element.get("name_attr")) else 1
            scored.append((score, -(idx + specificity), element))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return scored[0][2]


# ── Selector ladder ─────────────────────────────────────────────────────────

def _effective_role(element: Dict[str, Any]) -> str:
    role = normalise(element.get("role"))
    if role and role not in ("generic",):
        return role
    tag = element.get("tag") or ""
    ctype = element.get("type") or ""
    if ctype in ROLE_BY_CONTROL_TYPE:
        return ROLE_BY_CONTROL_TYPE[ctype]
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "select":
        return "combobox"
    if tag in ("input", "textarea"):
        return "textbox"
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return "heading"
    return ""


def _accessible_name(element: Dict[str, Any]) -> str:
    for field in ("label", "text", "placeholder", "name_attr", "id"):
        value = str(element.get(field) or "").strip()
        if value:
            return value
    return ""


def build_selector_candidates(
    element: Dict[str, Any],
    target: str = "",
) -> List[SelectorCandidate]:
    """
    Build the ordered selector ladder for one observed element.

    Each entry is a *strategy* description; the Playwright executor turns it
    into a real locator at run time.
    """
    if not element:
        return []

    source = element.get("element_id") or element.get("page_id") or "observed"
    obs = element.get("observation_status") or "observed"
    candidates: List[SelectorCandidate] = []

    def _add(strategy: str, value: str, role: Optional[str] = None,
             name: Optional[str] = None, strict: bool = True) -> None:
        if not value:
            return
        if any(c.strategy == strategy and c.value == value for c in candidates):
            return
        candidates.append(SelectorCandidate(
            strategy=strategy,
            value=value,
            role=role,
            name=name,
            strict=strict,
            source=source,
            observation_status=obs,
        ))

    role = _effective_role(element)
    accessible_name = _accessible_name(element) or str(target or "").strip()

    # 1. accessibility role + name
    if role and accessible_name:
        _add("role_name", f"role={role}|name={accessible_name}", role=role, name=accessible_name)
    elif role:
        _add("role_name", f"role={role}", role=role, strict=False)

    # 2. stable test identifier (only if actually observed)
    raw = element.get("source") if isinstance(element.get("source"), dict) else {}
    for attr in TEST_ID_ATTRIBUTES:
        observed = raw.get(attr)
        if observed:
            _add("test_id", f"[{attr}={_css_escape(str(observed))}]")

    # 3. label
    label = str(element.get("label") or "").strip() or str(element.get("placeholder") or "").strip()
    if label:
        _add("label", label)

    # 4. stable attribute
    dom_id = str(element.get("id") or "").strip()
    if dom_id and _CSS_IDENT.match(dom_id):
        _add("attribute", f"#{dom_id}")
    name_attr = str(element.get("name_attr") or "").strip()
    if name_attr and _CSS_IDENT.match(name_attr):
        _add("attribute", f"[name={_css_escape(name_attr)}]")
    if element.get("placeholder"):
        _add("attribute", f"[placeholder={_css_escape(str(element['placeholder']))}]")

    # 5. observed CSS (id/name/tag-qualified — never nth-child)
    tag = element.get("tag") or ""
    if dom_id and _CSS_IDENT.match(dom_id):
        _add("css", f"#{dom_id}")
    if name_attr and tag:
        _add("css", f"{tag}[name={_css_escape(name_attr)}]")
    elif name_attr:
        _add("css", f"[name={_css_escape(name_attr)}]")
    if tag and accessible_name and tag in ("button", "a", "h1", "h2", "h3"):
        _add("css", f"{tag}:has-text({_css_escape(accessible_name)})")

    stable_classes = [c for c in str(element.get("class") or "").split() if _is_stable_class(c)]
    if tag and stable_classes and not dom_id and not name_attr:
        _add("css", f"{tag}.{stable_classes[0]}")

    # 6. XPath — only when evidence actually carries one
    observed_xpath = raw.get("xpath") or raw.get("xpath_selector")
    if observed_xpath:
        _add("xpath", str(observed_xpath))

    return candidates


def resolve_selectors(
    target: str,
    app_context: Any = None,
    elements: Optional[Sequence[Dict[str, Any]]] = None,
    min_score: float = 0.6,
) -> List[SelectorCandidate]:
    """
    Full pipeline: step target → observed element → ordered selector ladder.

    Returns ``[]`` when no observed element matches, which the planner then
    reports as an unsupported step rather than inventing a selector.
    """
    if elements is None:
        elements = collect_evidence_elements(app_context)
    element = find_target_element(target, elements, min_score=min_score)
    if not element:
        return []
    candidates = build_selector_candidates(element, target=target)
    element_id = element.get("element_id")
    if element_id:
        for candidate in candidates:
            candidate.source = f"{candidate.source}:{element_id}"
    return candidates


__all__ = [
    "TEST_ID_ATTRIBUTES", "STABLE_ATTRIBUTES", "ROLE_BY_CONTROL_TYPE",
    "normalise", "tokens", "score_element", "find_target_element",
    "collect_evidence_elements", "normalise_evidence_element",
    "build_selector_candidates", "resolve_selectors",
]
