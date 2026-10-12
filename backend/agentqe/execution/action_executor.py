"""
Phase 5 — Deterministic Action Executor.

Executes one :class:`ExecutionStepPlan` against a Playwright page. This is the
only place that knows how to translate a planned action into Playwright calls,
which keeps the Playwright API surface small and mockable.

Every action returns an :class:`ActionOutcome`; nothing raises out of here. A
failure is a *structured* outcome carrying a FailureCategory, so the calling
executor can record it, capture evidence, and continue.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.redaction import redact_text, redact_url
from agentqe.execution.schemas import (
    ActionType,
    AssertionResult,
    ExecutionStepPlan,
    FailureCategory,
    SelectorCandidate,
)

logger = logging.getLogger(__name__)

#: Playwright exception type names mapped to our failure categories. The class
#: is resolved lazily so the module imports cleanly without Playwright present.
_PLAYWRIGHT_ERROR_MAP = {
    "TimeoutError": FailureCategory.TIMEOUT,
    "PlaywrightTimeoutError": FailureCategory.TIMEOUT,
    "Error": FailureCategory.BROWSER_ERROR,
}


@dataclass
class ActionOutcome:
    """Result of running one step."""

    passed: bool
    action: str
    target: str = ""
    selector_used: Optional[str] = None
    selector_strategy: Optional[str] = None
    error: Optional[str] = None
    error_category: Optional[str] = None
    assertion: Optional[AssertionResult] = None
    duration_ms: float = 0.0
    page_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "action": self.action,
            "target": self.target,
            "selector_used": self.selector_used,
            "selector_strategy": self.selector_strategy,
            "error": self.error,
            "error_category": self.error_category,
            "assertion": self.assertion.to_dict() if self.assertion else None,
            "duration_ms": round(self.duration_ms, 2),
            "page_url": self.page_url,
            "metadata": dict(self.metadata),
        }


class StepNotExecutable(Exception):
    """Raised internally when a step cannot be attempted at all."""

    def __init__(self, reason: str, category: str = FailureCategory.EXECUTOR_ERROR):
        super().__init__(reason)
        self.reason = reason
        self.category = category


def classify_error(exc: BaseException) -> str:
    """
    Map a Playwright/PlayError exception to a Phase 5 failure category.

    Uses Playwright's own ``errors`` classes when available and falls back to
    message inspection, so classification also works with test doubles.
    """
    name = type(exc).__name__
    if name in _PLAYWRIGHT_ERROR_MAP:
        return _PLAYWRIGHT_ERROR_MAP[name]

    text = str(exc).lower()
    if "timeout" in text or "exceeded" in text and "timeout" in text:
        return FailureCategory.TIMEOUT
    if "net::" in text or "err_name" in text or "err_internet" in text:
        return FailureCategory.NETWORK_ERROR
    if "intercepts" in text and "pointer events" in text:
        return FailureCategory.ELEMENT_NOT_INTERACTABLE
    if "not visible" in text or "hidden" in text or "not enabled" in text:
        return FailureCategory.ELEMENT_NOT_INTERACTABLE
    if "strict mode violation" in text:
        return FailureCategory.ELEMENT_NOT_FOUND
    if "net::err" in text or "connection" in text or "unreachable" in text:
        return FailureCategory.NETWORK_ERROR
    return _PLAYWRIGHT_ERROR_MAP.get(name, FailureCategory.BROWSER_ERROR)


def _classify_not_found(exc: BaseException) -> str:
    """Playwright raises the same class for 'not found' and 'not interactable'."""
    text = str(exc).lower()
    for marker in (
        "not visible", "is hidden", "not enabled", "intercepts pointer events",
        "element is not", "not stable", "outside of the viewport",
    ):
        if marker in text:
            return FailureCategory.ELEMENT_NOT_INTERACTABLE
    return FailureCategory.ELEMENT_NOT_FOUND


class ActionExecutor:
    """
    Deterministic execution of a single planned step.

    Selector resolution walks the ladder produced by
    :mod:`agentqe.execution.selectors` in strict robustness order
    (role/name → test id → label → attribute → CSS → XPath) and never
    invents an ``nth-child`` chain.
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or get_execution_config()

    # ── Public API ──────────────────────────────────────────────────────
    def execute(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        started = time.time()
        if not step.supported:
            return ActionOutcome(
                passed=False, action=step.action, target=step.target,
                error=step.unsupported_reason or "step is not supported",
                error_category=step.unsupported_category or FailureCategory.UNSUPPORTED_ACTION,
                page_url=self._page_url(page),
            )
        try:
            outcome = self._dispatch(page, step)
        except StepNotExecutable as exc:
            outcome = ActionOutcome(
                passed=False, action=step.action, target=step.target,
                error=redact_text(exc.reason, 500), error_category=exc.category,
                page_url=self._page_url(page),
            )
        except Exception as exc:  # any Playwright failure becomes structured
            category = classify_error(exc)
            if category in (FailureCategory.BROWSER_ERROR, FailureCategory.TIMEOUT):
                refined = _classify_not_found(exc)
                if refined != FailureCategory.ELEMENT_NOT_FOUND:
                    category = refined
            outcome = ActionOutcome(
                passed=False, action=step.action, target=step.target,
                error=redact_text(str(exc), 500), error_category=category,
                page_url=self._page_url(page),
            )
        outcome.duration_ms = (time.time() - started) * 1000
        if not outcome.page_url:
            outcome.page_url = self._page_url(page)
        return outcome

    # ── Dispatch ───────────────────────────────────────────────────────
    def _dispatch(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        action = step.action
        handler = {
            ActionType.NAVIGATE: self._navigate,
            ActionType.CLICK: self._click,
            ActionType.FILL: self._fill,
            ActionType.SELECT: self._select,
            ActionType.CHECK: self._check,
            ActionType.UNCHECK: self._uncheck,
            ActionType.PRESS: self._press,
            ActionType.HOVER: self._hover,
            ActionType.SUBMIT: self._submit,
            ActionType.WAIT: self._wait,
            ActionType.SCREENSHOT: self._noop,
            ActionType.ASSERT_URL: self._assert_url,
            ActionType.ASSERT_TEXT: self._assert_text,
            ActionType.ASSERT_VISIBLE: self._assert_visible,
            ActionType.ASSERT_NOT_VISIBLE: self._assert_not_visible,
            ActionType.ASSERT_ELEMENT_EXISTS: self._assert_exists,
            ActionType.ASSERT_ELEMENT_ABSENT: self._assert_absent,
        }.get(action)

        if handler is None:
            raise StepNotExecutable(
                f"action '{action}' is not implemented by the deterministic executor",
                FailureCategory.UNSUPPORTED_ACTION,
            )
        return handler(page, step)

    # ── Navigation ─────────────────────────────────────────────────────
    def _navigate(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        url = step.target or step.value
        if not url:
            raise StepNotExecutable(
                "navigation step has no URL", FailureCategory.MISSING_TEST_DATA
            )
        timeout = step.timeout_ms or self.config.navigation_timeout_ms
        try:
            response = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        except Exception as exc:
            message = str(exc).lower()
            if "net::" in message or "err_name" in message or "err_connection" in message:
                raise StepNotExecutable(
                    redact_text(f"navigation to {redact_url(url)} failed: {exc}", 400),
                    FailureCategory.NAVIGATION_ERROR,
                ) from exc
            raise StepNotExecutable(
                redact_text(f"navigation to {redact_url(url)} failed: {exc}", 400),
                FailureCategory.NAVIGATION_ERROR,
            ) from exc

        status = getattr(response, "status", None) if response is not None else None
        if isinstance(status, int) and status >= 400:
            raise StepNotExecutable(
                f"navigation to {redact_url(url)} returned HTTP {status}",
                FailureCategory.NAVIGATION_ERROR,
            )
        return ActionOutcome(
            passed=True, action=step.action, target=url,
            page_url=self._page_url(page),
            metadata={"http_status": status, "navigation_timeout_ms": timeout},
        )

    # ── Interactions ───────────────────────────────────────────────────
    def _click(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        locator, used, strategy = self._resolve(page, step)
        self._require_interactable(locator, used)
        locator.click(timeout=step.timeout_ms or self.config.step_timeout_ms)
        return self._interaction_ok(step, used, strategy)

    def _fill(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        if step.value is None:
            raise StepNotExecutable(
                "fill step has no value to type", FailureCategory.MISSING_TEST_DATA
            )
        locator, used, strategy = self._resolve(page, step)
        self._require_interactable(locator, used)
        value = "" if step.value is None else str(step.value)
        locator.fill(value, timeout=step.timeout_ms or self.config.step_timeout_ms)
        outcome = self._interaction_ok(step, used, strategy)
        # Never record the typed value for credential-shaped targets.
        if outcome.metadata.get("sensitive_target"):
            outcome.metadata.pop("typed_value_length", None)
        else:
            outcome.metadata["typed_value_length"] = len(value)
        return outcome

    def _select(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        if step.value is None:
            raise StepNotExecutable(
                "select step has no option value", FailureCategory.MISSING_TEST_DATA
            )
        locator, used, strategy = self._resolve(page, step)
        self._require_interactable(locator, used)
        option = str(step.value)
        try:
            locator.select_option(value=option, timeout=step.timeout_ms or self.config.step_timeout_ms)
        except Exception:
            # Fall back to label/value matching, then to index-free text match.
            try:
                locator.select_option(label=option, timeout=step.timeout_ms or self.config.step_timeout_ms)
            except Exception:
                try:
                    locator.select_option(
                        value=option, timeout=step.timeout_ms or self.config.step_timeout_ms
                    )
                    raise
                except Exception as exc:
                    if "did not find" in str(exc).lower() or "no options" in str(exc).lower():
                        raise StepNotExecutable(
                            redact_text(f"option '{option}' not available in select '{step.target}': {exc}", 400),
                            FailureCategory.ELEMENT_NOT_FOUND,
                        ) from exc
                    raise
        return self._interaction_ok(step, used, strategy)

    def _check(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        return self._toggle(page, step, True)

    def _uncheck(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        return self._toggle(page, step, False)

    def _toggle(self, page: Any, step: ExecutionStepPlan, checked: bool) -> ActionOutcome:
        locator, used, strategy = self._resolve(page, step)
        self._require_interactable(locator, used)
        if checked:
            locator.check(timeout=step.timeout_ms or self.config.step_timeout_ms)
        else:
            locator.uncheck(timeout=step.timeout_ms or self.config.step_timeout_ms)
        return self._interaction_ok(step, used, strategy)

    def _hover(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        locator, used, strategy = self._resolve(page, step)
        locator.hover(timeout=step.timeout_ms or self.config.step_timeout_ms)
        return self._interaction_ok(step, used, strategy)

    def _press(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        key = str(step.value or step.target or "").strip()
        if not key:
            raise StepNotExecutable(
                "keyboard step has no key", FailureCategory.MISSING_TEST_DATA
            )
        target = step.target
        # A key step with a real element target presses on that element.
        if target and target != key and not key.lower().startswith(("control", "meta", "alt", "shift")):
            try:
                locator, used, strategy = self._resolve(page, step)
                locator.press(key, timeout=step.timeout_ms or self.config.step_timeout_ms)
                return self._interaction_ok(step, used, strategy)
            except StepNotExecutable:
                pass
        try:
            page.keyboard.press(key)
        except Exception as exc:
            raise StepNotExecutable(
                redact_text(f"keyboard press '{key}' failed: {exc}", 300),
                FailureCategory.BROWSER_ERROR,
            ) from exc
        return ActionOutcome(
            passed=True, action=step.action, target=key, selector_used=None,
            page_url=self._page_url(page), metadata={"pressed_key": key},
        )

    def _submit(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        target = step.target
        if target:
            try:
                locator, used, strategy = self._resolve(page, step)
                locator.evaluate("el => { if (el.form) el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit(); }")
                return self._interaction_ok(step, used, strategy)
            except StepNotExecutable:
                pass
        submitted = False
        try:
            page.evaluate("() => { const f = document.querySelector('form'); if (f) { f.requestSubmit ? f.requestSubmit() : f.submit(); return true; } return false; }")
            submitted = True
        except Exception as exc:
            raise StepNotExecutable(
                redact_text(f"form submission failed: {exc}", 300),
                FailureCategory.EXECUTOR_ERROR,
            ) from exc
        if not submitted:
            raise StepNotExecutable(
                "no form found on the current page to submit",
                FailureCategory.ELEMENT_NOT_FOUND,
            )
        return ActionOutcome(
            passed=True, action=step.action, target="form",
            page_url=self._page_url(page), metadata={"form_submitted": True},
        )

    def _wait(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        if step.metadata.get("wait_kind") == "selector" and step.target:
            target_ms = step.timeout_ms or self.config.step_timeout_ms
            self._wait_for_selector(page, step, target_ms)
            return ActionOutcome(
                passed=True, action=step.action, target=step.target,
                page_url=self._page_url(page),
                metadata={"waited_for": step.target, "timeout_ms": target_ms},
            )
        wait_ms = int(step.value if step.value is not None else 500)
        wait_ms = max(0, min(wait_ms, 60000))
        page.wait_for_timeout(wait_ms)
        return ActionOutcome(
            passed=True, action=step.action, target=str(wait_ms),
            page_url=self._page_url(page), metadata={"waited_ms": wait_ms},
        )

    def _noop(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        """Screenshot steps are handled by the executor's evidence collector."""
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            page_url=self._page_url(page), metadata={"handled_by": "evidence_collector"},
        )

    # ── Assertions ─────────────────────────────────────────────────────
    def _assert_url(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        expected = str(step.value or step.target or "")
        actual = self._page_url(page) or ""
        match = str(step.metadata.get("match") or "contains")
        ok = self._match(actual, expected, match)
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_URL, passed=ok,
            expected=expected, actual=redact_url(actual),
            message="URL matched" if ok else f"URL did not match ({match}) {expected!r}",
        )
        if not ok:
            return self._assertion_failed(step, assertion)
        return ActionOutcome(
            passed=True, action=step.action, target=expected,
            assertion=assertion, page_url=redact_url(actual),
            metadata={"match": match},
        )

    def _page_text(self, page: Any) -> str:
        """
        Read the visible page text, most reliable strategy first.

        Never raises for a missing strategy: an unreadable page is an empty
        string so the assertion simply fails with a clear message.
        """
        timeout = min(self.config.step_timeout_ms, 15000)
        for attempt in (
            lambda: page.locator("body").inner_text(timeout=timeout),
            lambda: page.inner_text("body", timeout=timeout),
            lambda: page.content(),
        ):
            try:
                text = attempt()
            except Exception:
                continue
            if text:
                return str(text)
        return ""

    def _assert_text(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        expected = str(step.value or step.target or "")
        if not expected:
            raise StepNotExecutable(
                "text assertion has no expected value", FailureCategory.MISSING_TEST_DATA
            )
        actual = self._page_text(page)
        ok = self._match(actual, expected, "contains")
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_TEXT, passed=ok,
            expected=expected, actual=redact_text(actual, 300),
            message="text present on page" if ok else f"text {expected!r} not found on page",
        )
        if not ok:
            return self._assertion_failed(step, assertion)
        return ActionOutcome(
            passed=True, action=step.action, target=expected,
            assertion=assertion, page_url=self._page_url(page),
        )

    def _assert_visible(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        locator, used, strategy = self._resolve(page, step)
        visible = self._is_visible(locator, step)
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_VISIBLE, passed=visible,
            expected="visible", actual="visible" if visible else "not visible",
            message="element is visible" if visible else f"element '{step.target}' is not visible",
        )
        if not visible:
            return self._assertion_failed(step, assertion, used, strategy)
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            assertion=assertion, page_url=self._page_url(page),
        )

    def _assert_not_visible(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        try:
            locator, used, strategy = self._resolve(page, step)
        except StepNotExecutable:
            # Absent is a pass for a "not visible" expectation.
            assertion = AssertionResult(
                index=step.index, assertion_type=ActionType.ASSERT_NOT_VISIBLE, passed=True,
                expected="not visible", actual="not present",
                message="element is absent, as expected",
            )
            return ActionOutcome(
                passed=True, action=step.action, target=step.target,
                assertion=assertion, page_url=self._page_url(page),
                metadata={"resolution": "absent"},
            )
        visible = self._is_visible(locator, step)
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_NOT_VISIBLE, passed=not visible,
            expected="not visible", actual="visible" if visible else "not visible",
            message="element is not visible" if not visible
            else f"element '{step.target}' is still visible",
        )
        if visible:
            return self._assertion_failed(step, assertion, used, strategy)
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            assertion=assertion, page_url=self._page_url(page),
        )

    def _assert_exists(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        try:
            locator, used, strategy = self._resolve(page, step)
            count = locator.count()
        except StepNotExecutable:
            count = 0
            used = strategy = None
        except Exception:
            count = 0
            used = strategy = None
        exists = count > 0
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_ELEMENT_EXISTS, passed=exists,
            expected="exists", actual=f"{count} match(es)",
            message="element exists" if exists else f"element '{step.target}' was not found",
        )
        if not exists:
            return self._assertion_failed(step, assertion, used, strategy)
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            assertion=assertion, page_url=self._page_url(page),
        )

    def _assert_absent(self, page: Any, step: ExecutionStepPlan) -> ActionOutcome:
        try:
            locator, used, strategy = self._resolve(page, step)
            count = locator.count()
        except StepNotExecutable:
            count, used, strategy = 0, None, None
        except Exception:
            count, used, strategy = 0, None, None
        absent = count == 0
        assertion = AssertionResult(
            index=step.index, assertion_type=ActionType.ASSERT_ELEMENT_ABSENT, passed=absent,
            expected="absent", actual=f"{count} match(es)",
            message="element is absent" if absent else f"element '{step.target}' is still present",
        )
        if not absent:
            return self._assertion_failed(step, assertion, used, strategy)
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            assertion=assertion, page_url=self._page_url(page),
        )

    # ── Selector resolution ────────────────────────────────────────────
    def _resolve(
        self, page: Any, step: ExecutionStepPlan,
    ) -> Tuple[Any, str, str]:
        """
        Walk the selector ladder for ``step``.

        Returns ``(locator, selector_used, selector_strategy)`` — the order
        callers unpack. A candidate is only accepted when it actually matches at
        least one element, so the ladder keeps advancing past stale evidence.
        Raises :class:`StepNotExecutable` with ``ELEMENT_NOT_FOUND`` when
        nothing resolves.

        Callers that treat "no match" as a meaningful answer (the assert-absent
        and assert-not-visible actions) catch that exception.
        """
        errors: List[str] = []
        candidates: List[SelectorCandidate] = list(step.selectors or [])

        for candidate in candidates:
            try:
                locator = self._locator_for(page, candidate, step)
                if locator is None:
                    errors.append(f"{candidate.strategy}: no locator")
                    continue
                if not self._matches(locator):
                    errors.append(f"{candidate.strategy}: 0 matches")
                    continue
                return locator, candidate.value, candidate.strategy
            except Exception as exc:
                errors.append(f"{candidate.strategy}: {redact_text(str(exc), 120)}")

        # Fallback: derive locators directly from the target text/label. This is
        # still deterministic and still never produces an nth-child chain.
        target = (step.target or "").strip()
        if target:
            for builder, strategy in (
                (lambda: page.get_by_role("button", name=target, exact=False), "role_name"),
                (lambda: page.get_by_role("textbox", name=target, exact=False), "role_name"),
                (lambda: page.get_by_role("link", name=target, exact=False), "role_name"),
                (lambda: page.get_by_label(target, exact=False), "label"),
                (lambda: page.get_by_placeholder(target, exact=False), "label"),
                (lambda: page.get_by_text(target, exact=False), "text"),
            ):
                try:
                    locator = builder()
                    if not self._matches(locator):
                        errors.append(f"{strategy}:fallback: 0 matches")
                        continue
                    return locator, f"text={target}", f"{strategy}:fallback"
                except Exception as exc:
                    errors.append(f"{strategy}:fallback: {redact_text(str(exc), 120)}")

        detail = "; ".join(errors[:6])
        raise StepNotExecutable(
            f"could not resolve a selector for '{step.target}'"
            + (f" (tried: {detail})" if detail else ""),
            FailureCategory.ELEMENT_NOT_FOUND,
        )

    def _locator_for(self, page: Any, candidate: SelectorCandidate, step: ExecutionStepPlan) -> Any:
        strategy = candidate.strategy
        value = candidate.value

        if strategy == "role_name":
            role = candidate.role or "button"
            name = candidate.name or step.target
            locator = page.get_by_role(role, name=name, exact=False)
            if not candidate.strict and locator.count() == 0:
                locator = page.get_by_role(role)
            return locator

        if strategy == "test_id":
            return page.locator(value)

        if strategy == "label":
            try:
                locator = page.get_by_label(value, exact=False)
                if locator.count() > 0:
                    return locator
            except Exception:
                pass
            return page.locator(value)

        if strategy in ("attribute", "css"):
            return page.locator(value)

        if strategy == "xpath":
            return page.locator(f"xpath={value}")

        # Unknown strategy: treat the value as a raw selector.
        return page.locator(value)

    @staticmethod
    def _matches(locator: Any) -> bool:
        """True when a locator resolves to at least one element."""
        try:
            return int(locator.count()) > 0
        except Exception:
            # If the count cannot be determined, assume it matches and let the
            # real interaction surface a Playwright error.
            return True

    def _require_interactable(self, locator: Any, used: str) -> None:
        """Fail fast with ELEMENT_NOT_INTERACTABLE instead of a raw Playwright error."""
        try:
            if not locator.is_visible(timeout=min(self.config.step_timeout_ms, 5000)):
                raise StepNotExecutable(
                    f"element resolved by '{used}' is not visible",
                    FailureCategory.ELEMENT_NOT_INTERACTABLE,
                )
        except StepNotExecutable:
            raise
        except Exception as exc:
            text = str(exc).lower()
            if "not visible" in text or "hidden" in text:
                raise StepNotExecutable(
                    f"element resolved by '{used}' is not visible",
                    FailureCategory.ELEMENT_NOT_INTERACTABLE,
                ) from exc

    def _is_visible(self, locator: Any, step: ExecutionStepPlan) -> bool:
        try:
            return bool(locator.is_visible(timeout=min(self.config.step_timeout_ms, 5000)))
        except Exception:
            try:
                return locator.count() > 0
            except Exception:
                return False

    def _wait_for_selector(self, page: Any, step: ExecutionStepPlan, timeout_ms: int) -> None:
        try:
            self._resolve(page, step)
        except StepNotExecutable as exc:
            raise StepNotExecutable(
                redact_text(f"wait target never appeared: {exc.reason}", 300),
                FailureCategory.TIMEOUT,
            ) from exc
        page.wait_for_timeout(min(200, timeout_ms))

    # ── Helpers ────────────────────────────────────────────────────────
    def _interaction_ok(self, step: ExecutionStepPlan, used: str, strategy: str) -> ActionOutcome:
        from agentqe.execution.redaction import is_sensitive_name
        return ActionOutcome(
            passed=True, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            page_url=self._page_url(None),
            metadata={"sensitive_target": bool(is_sensitive_name(step.target))},
        )

    def _assertion_failed(
        self, step: ExecutionStepPlan, assertion: AssertionResult,
        used: Optional[str] = None, strategy: Optional[str] = None,
    ) -> ActionOutcome:
        return ActionOutcome(
            passed=False, action=step.action, target=step.target,
            selector_used=used, selector_strategy=strategy,
            error=assertion.message, error_category=FailureCategory.ASSERTION_FAILED,
            assertion=assertion,
        )

    @staticmethod
    def _match(actual: str, expected: str, mode: str) -> bool:
        if not expected:
            return False
        actual_l = (actual or "").lower()
        expected_l = expected.lower()
        if mode == "exact":
            return actual_l.strip() == expected_l.strip()
        if mode == "regex":
            import re
            try:
                return re.search(expected, actual or "") is not None
            except re.error:
                return False
        return expected_l in actual_l

    @staticmethod
    def _page_url(page: Any) -> Optional[str]:
        if page is None:
            return None
        try:
            url = str(getattr(page, "url", "") or "")
            return redact_url(url) if url else None
        except Exception:
            return None


__all__ = ["ActionExecutor", "ActionOutcome", "StepNotExecutable", "classify_error"]
