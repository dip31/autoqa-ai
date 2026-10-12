"""
Phase 5 — Execution Planner.

Converts a generated :class:`CandidateTest` (Phase 3) — optionally carrying
Phase 4 ranking provenance — into a deterministic :class:`ExecutionPlan` that an
executor can actually run.

Design rules (Part 4):

* Steps are derived **only** from the generated test, the ApplicationContext,
  the UnifiedApplicationModel / KnowledgeModel, and observed DOM/AX/visual/network
  evidence. Application behaviour is never invented.
* When required information is unknown, the step is marked
  ``supported=False`` with a reason and a structural failure category. The plan
  reports ``blocked`` / ``unsupported`` rather than guessing.
* Natural-language steps (what Phase 3 generators emit) are parsed with a
  deterministic, documented grammar. Unparseable steps are marked unsupported
  with the original text preserved as ``source_text``.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.redaction import is_sensitive_name, redact_text, sanitize_step_value
from agentqe.execution.schemas import (
    ActionType,
    EXECUTOR_BROWSER_USE,
    EXECUTOR_PLAYWRIGHT,
    ExecutionPlan,
    ExecutionStepPlan,
    FailureCategory,
    SELECTOR_STRATEGY_ORDER,
    SelectorCandidate,
)
from agentqe.execution.selectors import collect_evidence_elements, resolve_selectors

logger = logging.getLogger(__name__)

# ── Test-type → layer mapping ───────────────────────────────────────────────
UI_TEST_TYPES = {
    "ui", "e2e", "functional", "functional_ui", "browser", "end_to_end",
    "integration", "smoke", "regression", "usability", "accessibility",
}
API_TEST_TYPES = {"api", "rest", "backend", "service", "contract"}
NON_UI_TEST_TYPES = {"performance", "load", "stress", "security_scan", "visual", "unit"}

#: Actions the deterministic Playwright executor can perform.
SUPPORTED_ACTIONS = set(ActionType.ALL)

#: Natural-language verbs → ActionType, longest-match first at parse time.
_VERB_ACTIONS: List[Tuple[str, str]] = [
    ("navigate to", ActionType.NAVIGATE),
    ("navigate", ActionType.NAVIGATE),
    ("go to", ActionType.NAVIGATE),
    ("open", ActionType.NAVIGATE),
    ("browse to", ActionType.NAVIGATE),
    ("visit", ActionType.NAVIGATE),
    ("load the page", ActionType.NAVIGATE),
    ("load", ActionType.NAVIGATE),
    ("assert url", ActionType.ASSERT_URL),
    ("verify url", ActionType.ASSERT_URL),
    ("check url", ActionType.ASSERT_URL),
    ("expect url", ActionType.ASSERT_URL),
    ("url should", ActionType.ASSERT_URL),
    ("url contains", ActionType.ASSERT_URL),
    ("assert", ActionType.ASSERT_TEXT),
    ("verify", ActionType.ASSERT_TEXT),
    ("ensure", ActionType.ASSERT_TEXT),
    ("confirm", ActionType.ASSERT_TEXT),
    ("check that", ActionType.ASSERT_TEXT),
    ("expect", ActionType.ASSERT_TEXT),
    ("validate", ActionType.ASSERT_TEXT),
    ("fill in", ActionType.FILL),
    ("fill out", ActionType.FILL),
    ("fill", ActionType.FILL),
    ("type into", ActionType.FILL),
    ("type", ActionType.FILL),
    ("enter", ActionType.FILL),
    ("input", ActionType.FILL),
    ("select", ActionType.SELECT),
    ("choose", ActionType.SELECT),
    ("pick", ActionType.SELECT),
    ("uncheck", ActionType.UNCHECK),
    ("check", ActionType.CHECK),
    ("tick", ActionType.CHECK),
    ("press", ActionType.PRESS),
    ("hover over", ActionType.HOVER),
    ("hover", ActionType.HOVER),
    ("click", ActionType.CLICK),
    ("tap", ActionType.CLICK),
    ("press the", ActionType.CLICK),
    ("submit", ActionType.SUBMIT),
    ("wait for", ActionType.WAIT),
    ("wait", ActionType.WAIT),
    ("pause", ActionType.WAIT),
    ("take a screenshot", ActionType.SCREENSHOT),
    ("capture a screenshot", ActionType.SCREENSHOT),
    ("screenshot", ActionType.SCREENSHOT),
]

_ASSERT_NEGATIVE = re.compile(
    r"(?i)\b(not visible|is not visible|should not|does not|doesn't|is absent|"
    r"no longer|not present|is hidden)\b"
)
_ASSERT_ELEMENT_EXISTS = re.compile(
    r"(?i)\b(element|control|button|link|field|input|option)\b.*\b(exists?|is present|is displayed|is rendered)\b"
)
_ASSERT_URL = re.compile(r"(?i)\burl\b")
#: "check the Terms checkbox" targets a control, so "check" means tick it.
_CHECKBOX_TARGET = re.compile(
    r"(?i)\b(checkbox|check\s+box|radio|tick\s+box|terms|opt[\s-]?in|"
    r"consent|agree|subscribe|newsletter|remember\s+me)\b"
)
_QUOTED = re.compile(r"[\"'‘]([^\"'’]{1,120})[\"'’]")
_WITH_VALUE = re.compile(r"(?i)\bwith\b\s+(.+)$")
_VALUE_IS = re.compile(r"(?i)\b(?:value|as|equal to|equals|with value|is)\b\s*(.+)$")
_NUMBER_MS = re.compile(r"(\d{1,6})\s*(ms|milliseconds?|s|seconds?)", re.I)
_NUMBER = re.compile(r"^(\d{1,6})$")
_WHITESPACE = re.compile(r"\s+")


def _clean_step_text(text: Any) -> str:
    """Normalise a step into a single-line string with ordered numbering removed."""
    if text is None:
        return ""
    raw = str(text).strip()
    raw = re.sub(r"^\s*(?:step\s*)?\d+[.):\-]\s*", "", raw, flags=re.I)
    raw = raw.replace("\n", " ").replace("\t", " ")
    return _WHITESPACE.sub(" ", raw).strip()


def _strip_quotes(text: str) -> str:
    return text.strip().strip("\"'‘’ ").strip()


def _first_verb(text: str) -> Tuple[str, str]:
    """Return (matched_verb, remainder) using the longest matching verb."""
    lowered = text.lower()
    best: Tuple[int, str, str] = (-1, "", "")
    for phrase, action in _VERB_ACTIONS:
        if lowered.startswith(phrase):
            if len(phrase) > best[0]:
                best = (len(phrase), phrase, action)
    if best[0] < 0:
        # allow a leading "then" / "and then" / "next"
        stripped = re.sub(r"(?i)^(then|and then|next|after that|finally)\s+", "", text)
        if stripped != text:
            return _first_verb(stripped)
        return ("", text)
    return best[1], text[len(best[1]):].strip(" :,-")


class ExecutionPlanner:
    """
    Deterministic CandidateTest → ExecutionPlan planner.

    ``config`` is read for safe test-data substitution; the planner never
    touches real credentials.
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or get_execution_config()

    # ── Public API ──────────────────────────────────────────────────────
    def plan(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext] = None,
        base_url: Optional[str] = None,
        rank_position: Optional[int] = None,
    ) -> ExecutionPlan:
        test_id = getattr(test, "test_id", "") or "unknown"
        plan = ExecutionPlan(
            test_id=test_id,
            title=str(getattr(test, "title", "") or ""),
            test_type=str(getattr(test, "test_type", "UI") or "UI"),
            target_url=self._resolve_target_url(test, application_context, base_url),
            preconditions=[str(p) for p in (getattr(test, "preconditions", None) or []) if p],
            evidence_refs=[str(r) for r in (getattr(test, "evidence_refs", None) or []) if r],
        )
        if rank_position is not None:
            plan.metadata["rank_position"] = rank_position
        if base_url:
            plan.metadata["base_url"] = base_url
        plan.layer = self._resolve_layer(test)
        plan.expected_outcomes = self._expected_outcomes(test)

        # 1. Explicitly non-automatable tests are skipped, not blocked or failed.
        if getattr(test, "automatable", True) is False:
            plan.status_hint = "skipped"
            plan.unsupported_reason = (
                "the candidate test is marked automatable=False"
            )
            plan.allowed_executors = []
            plan.metadata["skip_reason"] = "not_automatable"
            return plan

        # 2. Hard blocks next: a blocked test is never planned further.
        blocked_reason = self._blocked_reason(test)
        if blocked_reason:
            plan.status_hint = "blocked"
            plan.blocked_reason = blocked_reason
            plan.allowed_executors = []
            plan.metadata["blocking_source"] = "candidate_test"
            return plan

        # 2. Non-UI tests are reported as unsupported by the Playwright engine.
        if plan.layer != "ui":
            plan.status_hint = "unsupported"
            plan.unsupported_reason = (
                f"test_type '{plan.test_type}' maps to the '{plan.layer}' layer, "
                "which the Phase 5 deterministic UI executor does not cover"
            )
            plan.allowed_executors = []
            plan.metadata["unsupported_category"] = FailureCategory.UNSUPPORTED_ACTION
            return plan

        # 3. Build steps.
        raw_steps = self._raw_steps(test)
        if not raw_steps:
            plan.steps.append(ExecutionStepPlan(
                index=0,
                action=ActionType.NAVIGATE,
                target=plan.target_url,
                description="Navigate to the application entry point",
                source_text="",
                supported=bool(plan.target_url),
                unsupported_reason="" if plan.target_url else "no target URL is known for this test",
                unsupported_category="" if plan.target_url else FailureCategory.MISSING_TEST_DATA,
                metadata={"derived_from": "plan.target_url"},
            ))
        else:
            elements = collect_evidence_elements(application_context)
            for index, raw in enumerate(raw_steps):
                plan.steps.append(self._plan_step(index, raw, test, plan, elements))

        # 4. A plan with zero executable steps is not executable.
        if not plan.supported_steps:
            plan.status_hint = "unsupported"
            plan.unsupported_reason = (
                "no step of this test could be mapped to a supported deterministic action"
            )
            plan.metadata["unsupported_category"] = FailureCategory.UNSUPPORTED_ACTION
            return plan

        # 5. Optional Browser Use, only where the plan explicitly allows it AND
        #    the deployment actually enables it. A plan never *permits* an
        #    executor that configuration has switched off.
        if self._needs_agentic_help(plan) and self.config.browser_use_enabled:
            plan.allowed_executors = [EXECUTOR_PLAYWRIGHT, EXECUTOR_BROWSER_USE]
            plan.metadata["agentic_allowed"] = True
            plan.metadata["agentic_reason"] = (
                "one or more steps could not be resolved deterministically from observed evidence"
            )
        elif self._needs_agentic_help(plan):
            plan.metadata["agentic_candidate"] = True
            plan.metadata["agentic_blocked_reason"] = (
                "Browser Use is disabled by configuration; the deterministic "
                "Playwright executor will be used alone"
            )
        return plan

    # ── Step parsing ────────────────────────────────────────────────────
    def _plan_step(
        self,
        index: int,
        raw: Any,
        test: CandidateTest,
        plan: ExecutionPlan,
        elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        """Dispatch one raw step (natural-language sentence or structured dict)."""
        if isinstance(raw, dict):
            return self._plan_dict_step(index, raw, test, plan, elements)
        return self._plan_step_from_text(index, _clean_step_text(raw), test, plan, elements)

    def _plan_dict_step(
        self,
        index: int,
        raw: Dict[str, Any],
        test: CandidateTest,
        plan: ExecutionPlan,
        elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        text = _clean_step_text(raw.get("description") or raw.get("text") or raw.get("step") or "")
        action = str(raw.get("action") or raw.get("type") or "").strip().lower()
        target = _strip_quotes(str(raw.get("target") or raw.get("selector_hint") or raw.get("field") or ""))
        value = raw.get("value", raw.get("action_value"))
        expected = raw.get("expected") or raw.get("expected_result")
        #: An explicit selector supplied by the generator is authoritative; it is
        #: placed first in the ladder because it came from observed evidence.
        explicit_selector = str(
            raw.get("selector") or raw.get("css_selector") or raw.get("xpath") or ""
        ).strip()

        if not action:
            verb, remainder = _first_verb(text)
            if verb:
                parsed = self._plan_step_from_text(index, text, test, plan, elements)
                if raw.get("value") is not None and parsed.supported:
                    safe_value, note = sanitize_step_value(parsed.target, value, self.config)
                    parsed.value = safe_value
                    if note:
                        parsed.metadata["value_substitution"] = note
                if explicit_selector and parsed.supported:
                    self._prepend_explicit_selector(parsed, explicit_selector, raw)
                return parsed
            return self._unsupported(
                index, text, "structured step has neither an action nor a parseable sentence",
                FailureCategory.UNSUPPORTED_ACTION, test,
            )

        action = _canonical_action(action)
        if action not in SUPPORTED_ACTIONS:
            return self._unsupported(
                index, text or action, f"action '{action}' is not supported by the deterministic executor",
                FailureCategory.UNSUPPORTED_ACTION, test,
            )

        if action in (ActionType.NAVIGATE, ActionType.WAIT, ActionType.SCREENSHOT,
                      ActionType.SUBMIT, ActionType.ASSERT_URL):
            step = ExecutionStepPlan(
                index=index, action=action, target=target,
                description=text or action, source_text=text,
                expected=expected or "", evidence_refs=list(test.evidence_refs or []),
            )
            if action == ActionType.NAVIGATE and not target:
                step.target = plan.target_url
            if action == ActionType.WAIT and not target:
                return self._unsupported(
                    index, text, "wait step has no duration or target",
                    FailureCategory.MISSING_TEST_DATA, test,
                )
            return step

        if action in ActionType.ASSERTIONS:
            assertion_step = self._build_assertion_step(
                index, action, target, text, expected, test, elements
            )
            if explicit_selector and assertion_step.supported:
                self._prepend_explicit_selector(assertion_step, explicit_selector, raw)
            return assertion_step

        if not target:
            return self._unsupported(
                index, text or action, "structured step has no target element",
                FailureCategory.MISSING_TEST_DATA, test,
            )
        step = ExecutionStepPlan(
            index=index, action=action, target=target, value=value,
            description=text or f"{action} '{target}'", source_text=text,
            expected=expected or "", evidence_refs=list(test.evidence_refs or []),
        )
        if value is not None:
            safe_value, note = sanitize_step_value(target, value, self.config)
            step.value = safe_value
            if note:
                step.metadata["value_substitution"] = note
        step = self._attach_selectors(step, test, elements)
        if explicit_selector:
            self._prepend_explicit_selector(step, explicit_selector, raw)
        return step

    @staticmethod
    def _prepend_explicit_selector(
        step: ExecutionStepPlan, selector: str, raw: Dict[str, Any],
    ) -> None:
        """
        Put a generator-supplied selector at the head of the ladder.

        A supplied ``xpath``/``selector`` starting with ``/`` or ``(`` is treated
        as XPath; everything else is CSS. Positional CSS (``nth-child``) is
        rejected outright — the executor must not depend on DOM order.
        """
        if not selector:
            return
        looks_xpath = raw.get("xpath") is not None or selector.startswith(("/", "(", "./"))
        if ":nth-child" in selector or "nth-of-type" in selector:
            logger.warning(
                "[ExecutionPlanner] ignoring positional selector '%s' for step %s",
                selector, step.index,
            )
            return
        candidate = SelectorCandidate(
            strategy="xpath" if looks_xpath else "css",
            value=selector,
            strict=False,
            source="candidate_test_selector",
            observation_status="observed",
        )
        step.selectors = [
            c for c in step.selectors if not (c.strategy == candidate.strategy
                                             and c.value == candidate.value)
        ]
        step.selectors.insert(0, candidate)
        step.metadata["selector_source"] = "candidate_test_selector"
        step.metadata["explicit_selector"] = redact_text(selector, 200)

    def _plan_step_from_text(
        self, index: int, text: str, test: CandidateTest,
        plan: ExecutionPlan, elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        verb, remainder = _first_verb(text)
        if not verb:
            return self._unsupported(
                index, text, "could not determine an action verb for this step",
                FailureCategory.UNSUPPORTED_ACTION, test,
            )
        action = dict(_VERB_ACTIONS).get(verb, "")
        # "Check the Terms checkbox" is a checkbox action; only treat "check" as a
        # visibility assertion when the sentence actually describes visibility.
        if verb == "check" and _ASSERT_ELEMENT_EXISTS.search(remainder) \
                and not _CHECKBOX_TARGET.search(remainder):
            action = ActionType.ASSERT_VISIBLE
        if action in (ActionType.NAVIGATE,):
            return self._plan_navigate(index, text, verb, remainder, plan, test)
        if action in (ActionType.ASSERT_URL,):
            return self._plan_assert_url(index, text, verb, remainder, plan, test)
        if action in (ActionType.WAIT, ActionType.SCREENSHOT, ActionType.SUBMIT):
            return self._plan_simple(index, text, action, remainder, plan, test)
        if action in ActionType.ASSERTIONS:
            return self._plan_assertion(index, text, action, remainder, plan, test, elements)
        if action == ActionType.PRESS:
            key = _strip_quotes(remainder)
            if not key:
                return self._unsupported(index, text, "keyboard step has no key",
                                        FailureCategory.MISSING_TEST_DATA, test)
            return ExecutionStepPlan(
                index=index, action=ActionType.PRESS, target=key, value=key,
                description=f"Press {key}", source_text=text,
                expected=f"key '{key}' dispatched", evidence_refs=list(test.evidence_refs or []),
            )
        target, value = self._split_target_value(remainder, action)
        if not target:
            return self._unsupported(index, text, "interaction step has no target element",
                                    FailureCategory.MISSING_TEST_DATA, test)
        if action == ActionType.FILL and value is None:
            return self._unsupported(index, text, "fill step has no value to type",
                                    FailureCategory.MISSING_TEST_DATA, test)
        step = ExecutionStepPlan(
            index=index, action=action, target=target,
            description=f"{action} '{target}'", source_text=text,
            evidence_refs=list(test.evidence_refs or []),
        )
        if value is not None:
            safe_value, note = sanitize_step_value(target, value, self.config)
            step.value = safe_value
            if note:
                step.metadata["value_substitution"] = note
        return self._attach_selectors(step, test, elements)

    # ── Per-action builders ─────────────────────────────────────────────
    def _plan_navigate(
        self, index: int, text: str, verb: str, remainder: str,
        plan: ExecutionPlan, test: CandidateTest,
    ) -> ExecutionStepPlan:
        raw_target = _strip_quotes(remainder) or plan.target_url
        url = self._to_absolute_url(raw_target, plan.target_url)
        if not url:
            return self._unsupported(
                index, text, "navigation target is not a resolvable URL",
                FailureCategory.MISSING_TEST_DATA, test,
            )
        return ExecutionStepPlan(
            index=index, action=ActionType.NAVIGATE, target=url,
            description=f"Navigate to {url}", source_text=text,
            expected=f"URL is {url}", evidence_refs=list(test.evidence_refs or []),
            metadata={"derived_from": "step"},
        )

    def _plan_assert_url(
        self, index: int, text: str, verb: str, remainder: str,
        plan: ExecutionPlan, test: CandidateTest,
    ) -> ExecutionStepPlan:
        expected = _strip_quotes(remainder)
        if not expected:
            expected = plan.target_url
        if not expected:
            return self._unsupported(
                index, text, "URL assertion has no expected value",
                FailureCategory.MISSING_TEST_DATA, test,
            )
        return ExecutionStepPlan(
            index=index, action=ActionType.ASSERT_URL, target=expected, value=expected,
            description=f"Assert URL contains {expected}", source_text=text,
            expected=expected, evidence_refs=list(test.evidence_refs or []),
            metadata={"match": "contains"},
        )

    def _plan_simple(
        self, index: int, text: str, action: str, remainder: str,
        plan: ExecutionPlan, test: CandidateTest,
    ) -> ExecutionStepPlan:
        target = _strip_quotes(remainder)
        if action == ActionType.WAIT:
            match = _NUMBER_MS.search(remainder)
            if match:
                amount = int(match.group(1))
                unit = match.group(2).lower()
                ms = amount if unit.startswith("ms") or unit.startswith("milli") else amount * 1000
                return ExecutionStepPlan(
                    index=index, action=ActionType.WAIT, target=str(ms), value=ms,
                    description=f"Wait {ms}ms", source_text=text, expected=f"waited {ms}ms",
                    timeout_ms=min(ms + 1000, 60000), evidence_refs=list(test.evidence_refs or []),
                    metadata={"wait_kind": "duration"},
                )
            if _NUMBER.match(target or ""):
                return ExecutionStepPlan(
                    index=index, action=ActionType.WAIT, target=target, value=int(target),
                    description=f"Wait {target}ms", source_text=text, expected="waited",
                    timeout_ms=min(int(target) + 1000, 60000),
                    evidence_refs=list(test.evidence_refs or []),
                    metadata={"wait_kind": "duration"},
                )
            if not target:
                return self._unsupported(
                    index, text, "wait step has neither a duration nor a target",
                    FailureCategory.MISSING_TEST_DATA, test,
                )
            return ExecutionStepPlan(
                index=index, action=ActionType.WAIT, target=target,
                description=f"Wait for '{target}'", source_text=text,
                expected=target, evidence_refs=list(test.evidence_refs or []),
                metadata={"wait_kind": "selector"},
            )
        if action == ActionType.SUBMIT:
            return ExecutionStepPlan(
                index=index, action=ActionType.SUBMIT, target=target,
                description="Submit the enclosing form", source_text=text,
                expected="form submitted", evidence_refs=list(test.evidence_refs or []),
            )
        return ExecutionStepPlan(
            index=index, action=ActionType.SCREENSHOT, target=target,
            description=f"Capture screenshot {target}".strip(), source_text=text,
            expected="screenshot captured", evidence_refs=list(test.evidence_refs or []),
        )

    def _plan_assertion(
        self, index: int, text: str, action: str, remainder: str,
        plan: ExecutionPlan, test: CandidateTest, elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        quoted = _QUOTED.search(remainder)
        if quoted:
            target = quoted.group(1).strip()
            remainder = remainder.replace(quoted.group(0), " ").strip()
        else:
            target = _strip_quotes(
                re.sub(r"(?i)^(is|are|be|being|that|to|be visible|be present)\b", "", remainder).strip()
            )
            target = re.sub(
                r"(?i)\b(is|are)\s+(visible|displayed|present|shown|enabled|checked|"
                r"in the page|not|no longer|absent)\b.*$", "", target,
            ).strip()

        resolved_action = action
        if _ASSERT_NEGATIVE.search(remainder) and action in (
            ActionType.ASSERT_VISIBLE, ActionType.ASSERT_TEXT
        ):
            resolved_action = ActionType.ASSERT_NOT_VISIBLE
        if _ASSERT_ELEMENT_EXISTS.search(remainder) and action == ActionType.ASSERT_VISIBLE:
            resolved_action = ActionType.ASSERT_ELEMENT_EXISTS

        if not target:
            return self._unsupported(
                index, text, "assertion has no expected text or element",
                FailureCategory.MISSING_TEST_DATA, test,
            )
        return self._build_assertion_step(index, resolved_action, target, text, target, test, elements)

    def _build_assertion_step(
        self, index: int, action: str, target: str, text: str,
        expected: Optional[str], test: CandidateTest,
        elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        step = ExecutionStepPlan(
            index=index, action=action, target=target,
            value=expected if action == ActionType.ASSERT_TEXT else None,
            description=f"{action} '{target}'", source_text=text,
            expected=expected or target, evidence_refs=list(test.evidence_refs or []),
        )
        if action in (ActionType.ASSERT_VISIBLE, ActionType.ASSERT_NOT_VISIBLE,
                      ActionType.ASSERT_ELEMENT_EXISTS, ActionType.ASSERT_ELEMENT_ABSENT):
            return self._attach_selectors(step, test, elements)
        return step

    # ── Helpers ────────────────────────────────────────────────────────
    def _attach_selectors(
        self, step: ExecutionStepPlan, test: CandidateTest, elements: List[Dict[str, Any]],
    ) -> ExecutionStepPlan:
        """
        Attach the selector ladder for ``step.target``.

        An unresolved target is NOT an error here: a step may still succeed via
        a role/text-based lookup at run time, or via the optional agentic
        adapter. The Playwright executor reports ELEMENT_NOT_FOUND if it truly
        cannot be located.
        """
        if not step.target:
            return step
        candidates = resolve_selectors(step.target, elements=elements)
        if candidates:
            step.selectors = candidates
            step.metadata["selector_source"] = "observed_evidence"
            step.metadata["selector_strategies"] = [c.strategy for c in candidates]
        else:
            step.metadata["selector_source"] = "unresolved"
            step.metadata["agentic_candidate"] = True
        return step

    def _split_target_value(self, remainder: str, action: str) -> Tuple[str, Any]:
        """
        Split a step remainder into ``(target, value)``.

        Handles the shapes real generated tests use, without guessing when the
        sentence is genuinely ambiguous:

            "the Email field with 'x@y.z'"   -> ("Email", "x@y.z")
            "'x@y.z' into the Email field"   -> ("Email", "x@y.z")
            "the Sign in button"             -> ("Sign in button", None)
            "text 'Welcome' is visible"      -> ("Welcome", None)
        """
        raw = (remainder or "").strip()
        if not raw:
            return ("", None)

        wants_value = action in (ActionType.FILL, ActionType.SELECT)
        value: Any = None
        text = raw

        # 1. A quoted span is the value (for fill/select) or the expected text
        #    (for assertions). Extract it and work on what is left.
        quoted = list(_QUOTED.finditer(raw))
        if quoted:
            first = quoted[0]
            inner = first.group(1).strip()
            if wants_value:
                value = inner
                text = (raw[: first.start()] + " " + raw[first.end():]).strip()
            else:
                text = inner
        elif wants_value:
            # 2. No quotes: fall back to "with ..." / "value ..." phrasing.
            for pattern in (_WITH_VALUE, _VALUE_IS):
                match = pattern.search(raw)
                if match:
                    value = _strip_quotes(match.group(1))
                    text = _strip_quotes(raw[: match.start()])
                    break

        target = self._clean_target_text(text, action)
        if not target and not wants_value:
            target = self._clean_target_text(raw, action)
        return (target, value)

    @staticmethod
    def _clean_target_text(text: str, action: str) -> str:
        """Strip filler prepositions/articles and trailing control nouns."""
        cleaned = _strip_quotes(text or "")
        # Trailing assertion qualifiers: "'Welcome' is visible on the dashboard"
        cleaned = re.sub(
            r"(?i)\s*\b(?:is|are)\s+(?:visible|displayed|shown|present|enabled|disabled|"
            r"checked|selected|focused|not\s+\w+)\b.*$",
            "", cleaned,
        ).strip()
        cleaned = re.sub(r"(?i)\s*\bon\s+the\s+.*$", "", cleaned).strip()
        # Leading prepositions and articles (repeat: "into the Email" -> "Email").
        for _ in range(4):
            stripped = re.sub(
                r"(?i)^(?:and\s+then|then|and|next|the|a|an|on|to|at|into|in|inside|"
                r"with|within|from|using|via|of|for)\s+", "", cleaned,
            ).strip()
            if stripped == cleaned:
                break
            cleaned = stripped
        # Trailing control nouns.
        cleaned = re.sub(
            r"(?i)\s+(?:field|input|textbox|text\s+box|text\s+field|box|button|link|"
            r"checkbox|check\s+box|radio|radio\s+button|toggle|switch|dropdown|"
            r"drop\s+down|select|option|tab|menu|element|control|node|item|cell|"
            r"link\s+element|icon)\s*$",
            "", cleaned,
        ).strip()
        return _strip_quotes(cleaned)

    def _unsupported(
        self, index: int, text: str, reason: str, category: str, test: CandidateTest,
    ) -> ExecutionStepPlan:
        return ExecutionStepPlan(
            index=index, action=ActionType.WAIT, target="", source_text=text,
            description=reason, supported=False,
            unsupported_reason=redact_text(reason, 300),
            unsupported_category=category,
            evidence_refs=list(test.evidence_refs or []),
            metadata={"original_action": None},
        )

    def _raw_steps(self, test: CandidateTest) -> List[Any]:
        steps = getattr(test, "steps", None) or []
        if steps:
            return list(steps)
        metadata = getattr(test, "metadata", None) or {}
        if metadata.get("action"):
            step: Dict[str, Any] = {
                "action": metadata.get("action"),
                "value": metadata.get("action_value") or metadata.get("value"),
                "target": metadata.get("target") or metadata.get("field") or "",
            }
            # ``selector`` may be a bare string or a {"css": ..., "xpath": ...} map.
            selector = metadata.get("selector") or metadata.get("css_selector")
            if isinstance(selector, dict):
                step.update({k: v for k, v in selector.items() if v})
            elif selector:
                step["selector"] = selector
            if metadata.get("expected") or metadata.get("expected_result"):
                step["expected"] = metadata.get("expected") or metadata.get("expected_result")
            return [step]
        # Fall back to the single-line objective/description.
        for field in ("description", "title"):
            text = getattr(test, field, "")
            if text and len(str(text).split()) <= 25:
                return [str(text)]
        return []

    def _blocked_reason(self, test: CandidateTest) -> str:
        if getattr(test, "blocked_reason", None):
            return redact_text(str(test.blocked_reason), 300)
        return ""

    def _resolve_layer(self, test: CandidateTest) -> str:
        test_type = normalise_test_type(getattr(test, "test_type", "UI"))
        if test_type in UI_TEST_TYPES:
            return "ui"
        if test_type in API_TEST_TYPES:
            return "api"
        if test_type in NON_UI_TEST_TYPES:
            return test_type
        # Unknown test types are still treated as UI when steps look like UI steps.
        steps = getattr(test, "steps", None) or []
        if steps and any(isinstance(s, str) and _first_verb(s)[0] for s in steps):
            return "ui"
        return "ui"

    def _expected_outcomes(self, test: CandidateTest) -> List[str]:
        outcomes: List[str] = []
        expected = getattr(test, "expected_result", "") or ""
        if expected:
            outcomes.append(redact_text(expected, 300))
        metadata = getattr(test, "metadata", None) or {}
        for item in metadata.get("expected_outcomes") or []:
            outcomes.append(redact_text(item, 300))
        if not outcomes:
            assertion_steps = 0
            for step in getattr(test, "steps", None) or []:
                text = step if isinstance(step, str) else (step or {}).get("description", "")
                verb, _ = _first_verb(_clean_step_text(text))
                if verb in ("assert", "verify", "ensure", "confirm", "expect", "validate", "check that"):
                    assertion_steps += 1
            if assertion_steps:
                outcomes.append(f"{assertion_steps} explicit expectation(s) in the generated steps")
        return outcomes

    def _resolve_target_url(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext],
        base_url: Optional[str] = None,
    ) -> str:
        for candidate in (
            (getattr(test, "metadata", None) or {}).get("target_url"),
            getattr(test, "target", "") if _looks_like_url(getattr(test, "target", "")) else "",
            getattr(application_context, "url", "") if application_context else "",
            base_url or "",
        ):
            if candidate and _looks_like_url(candidate):
                return str(candidate).strip()
        return ""

    def _to_absolute_url(self, raw: str, base_url: str) -> str:
        text = _strip_quotes(raw or "")
        if not text:
            return base_url or ""
        if _looks_like_url(text):
            return text
        # A path or a bare page name.
        if text.startswith("/") and base_url:
            return urljoin(base_url, text)
        if _looks_like_url(base_url):
            return urljoin(base_url, "/" + text.lstrip("/"))
        return ""

    def _needs_agentic_help(self, plan: ExecutionPlan) -> bool:
        """True when Browser Use could plausibly add value (opt-in only)."""
        for step in plan.supported_steps:
            if step.metadata.get("agentic_candidate") and not step.selectors:
                return True
        return False


def normalise_test_type(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _looks_like_url(value: Any) -> bool:
    if not value:
        return False
    text = str(value).strip()
    if text.startswith(("http://", "https://", "file://", "about:")):
        return True
    parsed = urlparse(text)
    return bool(parsed.scheme and parsed.netloc)


def _canonical_action(action: str) -> str:
    mapping = {
        "goto": ActionType.NAVIGATE, "visit": ActionType.NAVIGATE, "open": ActionType.NAVIGATE,
        "navigate": ActionType.NAVIGATE, "goto_url": ActionType.NAVIGATE,
        "click": ActionType.CLICK, "tap": ActionType.CLICK, "press_button": ActionType.CLICK,
        "fill": ActionType.FILL, "type": ActionType.FILL, "input": ActionType.FILL,
        "enter": ActionType.FILL, "set_value": ActionType.FILL, "fill_text": ActionType.FILL,
        "select": ActionType.SELECT, "select_option": ActionType.SELECT,
        "check": ActionType.CHECK, "tick": ActionType.CHECK, "check_box": ActionType.CHECK,
        "uncheck": ActionType.UNCHECK, "untick": ActionType.UNCHECK,
        "press": ActionType.PRESS, "keyboard": ActionType.PRESS, "key": ActionType.PRESS,
        "hover": ActionType.HOVER,
        "submit": ActionType.SUBMIT, "submit_form": ActionType.SUBMIT,
        "wait": ActionType.WAIT, "sleep": ActionType.WAIT, "pause": ActionType.WAIT,
        "screenshot": ActionType.SCREENSHOT, "capture": ActionType.SCREENSHOT,
        "assert_url": ActionType.ASSERT_URL, "verify_url": ActionType.ASSERT_URL,
        "assert_text": ActionType.ASSERT_TEXT, "verify_text": ActionType.ASSERT_TEXT,
        "assert_visible": ActionType.ASSERT_VISIBLE, "verify_visible": ActionType.ASSERT_VISIBLE,
        "assert_not_visible": ActionType.ASSERT_NOT_VISIBLE,
        "assert_element_exists": ActionType.ASSERT_ELEMENT_EXISTS,
        "assert_element_absent": ActionType.ASSERT_ELEMENT_ABSENT,
    }
    normalised = re.sub(r"[^a-z0-9]+", "_", str(action or "").strip().lower()).strip("_")
    return mapping.get(normalised, normalised)


__all__ = ["ExecutionPlanner", "normalise_test_type", "SELECTOR_STRATEGY_ORDER"]
