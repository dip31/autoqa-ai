"""
Phase 1.5F — Confidence model.

EVIDENCE answers "where did this information come from?" (``evidence_refs``).
CONFIDENCE answers "how strongly do the available signals support this
correlation/inference?" — and is only produced where a documented formula
exists.

Hard rules implemented here
---------------------------
* Confidence is **only** attached to fusion correlations / inferred
  relationships. Raw observations do not get a confidence.
* Every returned confidence comes with a ``basis`` string that states the
  formula and the inputs, so it can be audited in the UI.
* When no meaningful calculation exists the functions return ``(None, None)``.
  A ``None`` confidence is always preferable to a fabricated value such as a
  blanket 0.5.
* Nothing here is a model/ML probability — these are deterministic
  signal-agreement scores.
"""

from typing import Any, Dict, List, Optional, Tuple

#: Multipliers applied by ``correlation_confidence`` based on how many
#: *independent* modalities agreed. One agreeing signal can be coincidence;
#: three agreeing signals rarely are.
_CORROBORATION_MULTIPLIER = {0: 0.0, 1: 0.80, 2: 0.90, 3: 1.00}

#: Signal weights for UI -> API association.
UI_API_SIGNAL_WEIGHTS = {
    "form_action_path_match": 0.50,
    "http_method_match": 0.15,
    "endpoint_observed_on_same_page": 0.20,
    "label_path_keyword_overlap": 0.15,
}

#: An association is only emitted when at least one of these strong signals is
#: present. "Seen on the same page" alone is NOT enough to claim causation.
UI_API_STRONG_SIGNALS = ("form_action_path_match", "label_path_keyword_overlap")

SIGNAL_AGREEMENT_THRESHOLD = 0.5


def clamp_confidence(value: Optional[float]) -> Optional[float]:
    """Return ``value`` clamped to [0, 1], or ``None`` if not a number."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, v)), 4)


def correlation_confidence(
    score: Optional[float],
    signals: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Confidence for a cross-modal correlation (e.g. visual element merged into a
    DOM control).

    Formula::

        agreeing = number of signals (text, bbox, role) scoring >= 0.5
        confidence = correlation_score * corroboration_multiplier[agreeing]
        multiplier = {1: 0.80, 2: 0.90, 3: 1.00}

    Rationale: the correlation score already blends the signals, but a score
    reached through a single modality deserves less trust than the same score
    reached through three. Returns ``(None, None)`` when there is no score.
    """
    if score is None:
        return None, None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None, None
    if s <= 0:
        return None, None

    signals = signals or {}
    bbox_unused = signals.get("bbox_used") is False
    agreeing_names: List[str] = []
    for signal_name, key in (("text", "text_similarity"),
                             ("bbox", "bbox_overlap"),
                             ("role", "role_compatibility")):
        if signal_name == "bbox" and bbox_unused:
            continue  # an unavailable signal can never count as agreement
        try:
            if float(signals.get(key, 0.0)) >= SIGNAL_AGREEMENT_THRESHOLD:
                agreeing_names.append(signal_name)
        except (TypeError, ValueError):
            continue

    agreeing = min(3, len(agreeing_names))
    multiplier = _CORROBORATION_MULTIPLIER.get(agreeing, 0.0)
    if multiplier == 0.0:
        return None, None

    value = clamp_confidence(s * multiplier)
    basis = (
        f"correlation_score={round(s, 4)} x corroboration_multiplier={multiplier} "
        f"({agreeing} agreeing signal(s): {', '.join(agreeing_names) or 'none'}). "
        f"Deterministic signal agreement, not a model probability."
    )
    return value, basis


def bbox_signal_unused(signals: Dict[str, Any]) -> bool:
    """True when the bbox signal was unavailable and must not count as agreement."""
    return (signals or {}).get("bbox_used") is False


def ui_api_confidence(matched_signals: Dict[str, bool]) -> Tuple[Optional[float], Optional[str]]:
    """
    Confidence for a ``likely_triggers`` / ``submits_to`` association between a
    UI control (or form) and an observed API endpoint.

    Formula: sum of the weights of the signals that matched, capped at 1.0::

        form_action_path_match          0.50
        http_method_match               0.15
        endpoint_observed_on_same_page  0.20
        label_path_keyword_overlap      0.15

    Returns ``(None, None)`` when no strong signal is present — in that case the
    caller must not emit the relationship at all (co-occurrence on a page is not
    evidence of causation).
    """
    matched = [k for k, v in (matched_signals or {}).items() if v and k in UI_API_SIGNAL_WEIGHTS]
    if not any(s in matched for s in UI_API_STRONG_SIGNALS):
        return None, None

    total = sum(UI_API_SIGNAL_WEIGHTS[k] for k in matched)
    value = clamp_confidence(total)
    basis = (
        "sum of matched UI/API signal weights ["
        + ", ".join(f"{k}={UI_API_SIGNAL_WEIGHTS[k]}" for k in sorted(matched))
        + f"] = {value}. Deterministic signal agreement, not a model probability."
    )
    return value, basis


def semantic_role_confidence(rule_id: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Semantic roles are produced by deterministic rules, which do not yield a
    calibrated probability. We therefore return ``None`` and rely on
    ``semantic_role_status`` + ``inference_reason`` for explainability.

    Kept as a named function so future LLM/VLM engines have an obvious seam.
    """
    return None, None


def flow_confidence(observed_steps: int, total_steps: int) -> Tuple[Optional[float], Optional[str]]:
    """
    Confidence for a reconstructed user flow = fraction of its steps that were
    directly observed during the crawl.

    A flow whose every step is inferred (e.g. a login the crawler never
    performed) gets a low value, not a flattering one. Returns ``(None, None)``
    for empty flows.
    """
    if not total_steps:
        return None, None
    value = clamp_confidence(float(observed_steps) / float(total_steps))
    basis = (
        f"{observed_steps}/{total_steps} flow steps directly observed during the crawl; "
        "remaining steps are deterministic inferences."
    )
    return value, basis
