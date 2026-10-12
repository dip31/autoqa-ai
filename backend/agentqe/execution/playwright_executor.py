"""
Phase 5 — Playwright Test Executor (PRIMARY ENGINE).

Playwright is the deterministic execution engine for AgentQE. This executor
owns the whole browser lifecycle for a single test:

    new browser context (isolated per test)
        → start tracing (optional)
        → attach evidence listeners
        → run the ExecutionPlan step by step
        → stop tracing, close context
        → build a structured ExecutionResult

Guarantees:

* **Isolation** — a fresh, isolated browser context per test. No shared state.
* **Bounded** — an overall timeout and a per-step timeout. A timeout produces
  ``status="timeout"``, never a generic error, and never hangs.
* **Non-fatal failures** — every failure is a structured result; a raised
  exception never escapes :meth:`execute`.
* **Redacted** — no value, header, cookie, or token is recorded.
* **Playwright is required, Browser Use is not** — if Playwright is missing the
  executor returns a structured ``error`` result rather than raising.

Browser Use is only consulted via :class:`IBrowserAgentExecutor`, and only
when the plan and configuration explicitly allow it.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from agentqe.execution.action_executor import ActionExecutor
from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.evidence_collector import (
    PlaywrightEvidenceCollector,
    artifact_reference,
    trace_reference,
)
from agentqe.execution.interfaces import ITestExecutor
from agentqe.execution.redaction import redact_text, redact_url
from agentqe.execution.schemas import (
    ActionType,
    EXECUTOR_NONE,
    EXECUTOR_PLAYWRIGHT,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStepPlan,
    FailureCategory,
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    STATUS_UNSUPPORTED,
    StepResult,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None
    PlaywrightError = Exception
    PlaywrightTimeoutError = Exception


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlaywrightTestExecutor(ITestExecutor):
    """
    Deterministic UI test executor backed by Playwright.

    Usage::

        executor = PlaywrightTestExecutor()
        result = executor.execute(test, app_context)          # plans + runs
        result = executor.execute_plan(plan, test, app_context)  # runs a plan
    """

    name = EXECUTOR_PLAYWRIGHT

    def __init__(
        self,
        config: Optional[ExecutionConfig] = None,
        playwright_factory: Any = None,
        action_executor: Optional[ActionExecutor] = None,
    ):
        """
        Args:
            config: Execution configuration (defaults to the process config).
            playwright_factory: Injection point for tests — a zero-arg callable
                returning a Playwright context manager. Defaults to
                ``sync_playwright``.
            action_executor: Injection point for a custom action executor.
        """
        self.config = config or get_execution_config()
        self._playwright_factory = playwright_factory or sync_playwright
        self.actions = action_executor or ActionExecutor(self.config)

    @property
    def is_available(self) -> bool:
        return bool(self.config.playwright_enabled and self._playwright_factory is not None)

    # ── Public API ──────────────────────────────────────────────────────
    def execute(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext] = None,
        plan: Optional[ExecutionPlan] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        """Plan (if needed) and execute one test."""
        cfg = config or self.config
        if plan is None:
            from agentqe.execution.execution_planner import ExecutionPlanner
            plan = ExecutionPlanner(cfg).plan(test, application_context)
        return self.execute_plan(plan, test=test, application_context=application_context, config=cfg)

    def execute_plan(
        self,
        plan: ExecutionPlan,
        test: Optional[CandidateTest] = None,
        application_context: Optional[ApplicationContext] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        cfg = config or self.config
        started_wall = time.time()
        result = self._base_result(plan, test)
        result.started_at = _utc_now()

        # 1. Non-runnable plans short-circuit without launching a browser.
        preflight = self._preflight(plan, result)
        if preflight is not None:
            return preflight

        if not self.is_available:
            return self._fail_fast(
                result, plan,
                "Playwright is not available in this environment",
                FailureCategory.EXECUTOR_ERROR, started_wall,
            )

        # 2. Run with an isolated browser context.
        try:
            with self._playwright_factory() as playwright:
                browser = self._launch(playwright, cfg)
                if browser is None:
                    return self._fail_fast(
                        result, plan,
                        f"Playwright browser '{cfg.playwright_browser}' could not be launched",
                        FailureCategory.BROWSER_ERROR, started_wall,
                    )
                context = None
                try:
                    context = browser.new_context(
                        viewport={
                            "width": cfg.viewport_width,
                            "height": cfg.viewport_height,
                        },
                        ignore_https_errors=True,
                    )
                    context.set_default_timeout(cfg.step_timeout_ms)
                    context.set_default_navigation_timeout(cfg.navigation_timeout_ms)
                    page = context.new_page()
                    self._run_steps(plan, result, page, cfg, started_wall)
                finally:
                    if context is not None:
                        try:
                            context.close()
                        except Exception:
                            pass
                    try:
                        browser.close()
                    except Exception:
                        pass
        except PlaywrightTimeoutError as exc:
            result.status = STATUS_TIMEOUT
            result.error_category = FailureCategory.TIMEOUT
            result.error = redact_text(
                f"execution exceeded the {cfg.execution_timeout_ms}ms budget: {exc}", 500
            )
        except Exception as exc:
            result.status = STATUS_ERROR
            result.error_category = FailureCategory.EXECUTOR_ERROR
            result.error = redact_text(f"executor error: {exc}", 500)
            logger.warning("[PlaywrightExecutor] executor error: %s", exc)
        finally:
            result.completed_at = _utc_now()
            result.duration_ms = round((time.time() - started_wall) * 1000, 2)

        self._finalise(result, plan)
        return result

    # ── Step loop ──────────────────────────────────────────────────────
    def _run_steps(
        self,
        plan: ExecutionPlan,
        result: ExecutionResult,
        page: Any,
        cfg: ExecutionConfig,
        started_wall: float,
    ) -> None:
        collector = PlaywrightEvidenceCollector(cfg, execution_id=result.execution_id)
        collector.start(result.execution_id, page)

        runnable = [s for s in plan.steps if s.supported]
        result.steps_total = len(plan.steps)

        try:
            if cfg.screenshots_enabled:
                meta = collector.capture_screenshot("initial", step_index=None)
                if meta:
                    result.screenshots.append(meta)

            for step in runnable:
                elapsed = (time.time() - started_wall) * 1000
                if elapsed >= cfg.execution_timeout_ms:
                    self._record_timeout(result, step, cfg, collector, page)
                    break

                step_result = self._run_step(step, page, cfg, collector, result)
                result.steps.append(step_result.to_dict())

                if step.action in ActionType.ASSERTIONS and step_result.assertion:
                    assertion = step_result.assertion
                    result.assertions.append(
                        assertion.to_dict() if hasattr(assertion, "to_dict") else dict(assertion)
                    )
                    result.assertions_total += 1
                    if assertion.passed:
                        result.assertions_passed += 1
                    else:
                        result.assertions_failed += 1

                if step_result.status != STATUS_PASSED:
                    if step.optional:
                        continue
                    result.failed_step = step.index
                    result.status = (
                        STATUS_TIMEOUT
                        if step_result.error_category == FailureCategory.TIMEOUT
                        else STATUS_FAILED
                    )
                    result.error = step_result.error
                    result.error_category = step_result.error_category
                    self._capture_failure_screenshot(collector, result, step)
                    break

                result.steps_completed += 1
                if cfg.screenshot_per_step:
                    meta = collector.capture_screenshot(
                        f"step{step.index}_{step.action}", step_index=step.index
                    )
                    if meta:
                        result.screenshots.append(meta)

            if result.status in (STATUS_PASSED, "", None) and result.failed_step is None:
                result.status = STATUS_PASSED
            if cfg.screenshots_enabled and result.status != STATUS_PASSED:
                meta = collector.capture_screenshot("final", step_index=None)
                if meta:
                    result.screenshots.append(meta)
        finally:
            bundle = collector.finish(self._page_url(page))
            self._absorb_evidence(result, bundle)

    def _run_step(
        self,
        step: ExecutionStepPlan,
        page: Any,
        cfg: ExecutionConfig,
        collector: PlaywrightEvidenceCollector,
        result: ExecutionResult,
    ) -> StepResult:
        step_start = time.time()
        step_result = StepResult(
            index=step.index,
            action=step.action,
            target=str(step.target or ""),
            description=step.description,
            started_at=_utc_now(),
        )
        if step.action == ActionType.SCREENSHOT:
            meta = collector.capture_screenshot(
                f"step{step.index}_screenshot", step_index=step.index
            )
            step_result.status = STATUS_PASSED
            step_result.duration_ms = round((time.time() - step_start) * 1000, 2)
            step_result.completed_at = _utc_now()
            step_result.screenshot_path = meta.get("path") if meta else None
            step_result.page_url = self._page_url(page)
            return step_result

        outcome = self.actions.execute(page, step)
        step_result.completed_at = _utc_now()
        step_result.duration_ms = outcome.duration_ms
        step_result.selector_used = outcome.selector_used
        step_result.selector_strategy = outcome.selector_strategy
        step_result.error = outcome.error
        step_result.error_category = outcome.error_category
        step_result.assertion = outcome.assertion
        step_result.page_url = outcome.page_url or self._page_url(page)
        step_result.status = STATUS_PASSED if outcome.passed else (
            STATUS_TIMEOUT if outcome.error_category == FailureCategory.TIMEOUT else STATUS_FAILED
        )
        if outcome.metadata:
            step_result.metadata = {
                k: v for k, v in outcome.metadata.items() if k != "sensitive_target"
            }
        if step.metadata.get("value_substitution"):
            step_result.metadata["value_substitution"] = redact_text(
                step.metadata["value_substitution"], 200
            )
        return step_result

    def _record_timeout(
        self, result: ExecutionResult, step: ExecutionStepPlan,
        cfg: ExecutionConfig, collector: PlaywrightEvidenceCollector, page: Any,
    ) -> None:
        result.steps.append(StepResult(
            index=step.index, action=step.action, target=str(step.target or ""),
            description=step.description, status= STATUS_TIMEOUT,
            error=f"execution budget of {cfg.execution_timeout_ms}ms exhausted before this step",
            error_category=FailureCategory.TIMEOUT,
            started_at=_utc_now(), completed_at=_utc_now(),
            page_url=self._page_url(page),
        ).to_dict())
        result.failed_step = step.index
        result.status = STATUS_TIMEOUT
        result.error_category = FailureCategory.TIMEOUT
        result.error = (
            f"execution exceeded the overall timeout of {cfg.execution_timeout_ms}ms "
            f"at step {step.index}"
        )
        self._capture_failure_screenshot(collector, result, step)

    # ── Helpers ────────────────────────────────────────────────────────
    def _launch(self, playwright: Any, cfg: Optional[ExecutionConfig] = None) -> Any:
        config = cfg or self.config
        launcher = getattr(playwright, config.playwright_browser, None)
        if launcher is None:
            return None
        args = ["--no-sandbox", "--disable-dev-shm-usage"] if config.playwright_headless else []
        try:
            return launcher.launch(headless=config.playwright_headless, args=args)
        except TypeError:
            # Test doubles may accept fewer kwargs.
            return launcher.launch(headless=config.playwright_headless)

    def _preflight(self, plan: ExecutionPlan, result: ExecutionResult) -> Optional[ExecutionResult]:
        """
        Reject a plan before launching a browser.

        Returns a completed ``ExecutionResult`` when the plan cannot be run, or
        ``None`` to proceed. A preflight rejection means *no browser was ever
        launched*, so the executor is recorded as ``none``.
        """
        if plan.status_hint == "skipped":
            result.status = STATUS_SKIPPED
            result.error = redact_text(
                plan.unsupported_reason or plan.blocked_reason or "test was skipped", 500
            )
            result.error_category = FailureCategory.UNSUPPORTED_ACTION
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        if plan.status_hint == "blocked":
            result.status = STATUS_BLOCKED
            result.error = redact_text(plan.blocked_reason or "test is blocked", 500)
            result.error_category = FailureCategory.MISSING_TEST_DATA
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        if plan.status_hint == "unsupported":
            result.status = STATUS_UNSUPPORTED
            result.error = redact_text(plan.unsupported_reason or "test is unsupported", 500)
            result.error_category = str(
                plan.metadata.get("unsupported_category") or FailureCategory.UNSUPPORTED_ACTION
            )
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        if not plan.steps:
            result.status = STATUS_UNSUPPORTED
            result.error = "execution plan contains no steps"
            result.error_category = FailureCategory.UNSUPPORTED_ACTION
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        if not plan.supported_steps:
            result.status = STATUS_UNSUPPORTED
            reasons = [
                f"step {s.index}: {s.unsupported_reason}"
                for s in plan.steps if not s.supported
            ][:5]
            result.error = redact_text(
                "no step of this test is executable (" + "; ".join(reasons) + ")", 500
            )
            result.error_category = FailureCategory.UNSUPPORTED_ACTION
            result.steps_total = len(plan.steps)
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        if not plan.target_url and not any(
            s.action == ActionType.NAVIGATE and s.target for s in plan.supported_steps
        ):
            result.status = STATUS_UNSUPPORTED
            result.error = "no navigation target is known for this test"
            result.error_category = FailureCategory.MISSING_TEST_DATA
            result.completed_at = _utc_now()
            return self._finalise(result, plan, executed=False)
        return None

    def _fail_fast(
        self, result: ExecutionResult, plan: ExecutionPlan, message: str,
        category: str, started_wall: float,
    ) -> ExecutionResult:
        result.status = STATUS_ERROR
        result.error = redact_text(message, 500)
        result.error_category = category
        result.completed_at = _utc_now()
        result.duration_ms = round((time.time() - started_wall) * 1000, 2)
        self._finalise(result, plan)
        return result

    def _base_result(self, plan: ExecutionPlan, test: Optional[CandidateTest]) -> ExecutionResult:
        result = ExecutionResult(test_id=plan.test_id, status="", executor=self.name)
        result.steps_total = len(plan.steps)
        result.start_url = redact_url(plan.target_url) if plan.target_url else None
        result.page_url = result.start_url
        result.metadata = {
            "test_title": plan.title,
            "layer": plan.layer,
            "test_type": plan.test_type,
            "target_url": redact_url(plan.target_url) if plan.target_url else None,
            "expected_outcomes": list(plan.expected_outcomes)[:10],
            "preconditions": list(plan.preconditions)[:10],
            "unsupported_steps": [
                {"index": s.index, "reason": s.unsupported_reason, "category": s.unsupported_category}
                for s in plan.steps if not s.supported
            ][:20],
        }
        result.evidence_refs = list(plan.evidence_refs)[:50]
        return result

    def _absorb_evidence(self, result: ExecutionResult, bundle: Dict[str, Any]) -> None:
        result.screenshots = list(bundle.get("screenshots") or [])
        result.console_errors = list(bundle.get("console_errors") or [])
        result.network_evidence = list(bundle.get("network_evidence") or []) + \
            list(bundle.get("network_failures") or [])
        result.trace_path = bundle.get("trace_path")
        artifacts = [
            artifact_reference(meta, result.execution_id) for meta in result.screenshots
        ]
        if result.trace_path:
            artifacts.append(trace_reference(result.trace_path, result.execution_id))
        result.artifacts = artifacts
        warnings = bundle.get("warnings") or []
        if warnings:
            result.metadata["evidence_warnings"] = [redact_text(w, 200) for w in warnings[:5]]

    def _capture_failure_screenshot(
        self, collector: PlaywrightEvidenceCollector,
        result: ExecutionResult, step: ExecutionStepPlan,
    ) -> None:
        meta = collector.capture_screenshot(
            f"failure_step{step.index}", step_index=step.index
        )
        if meta:
            result.screenshots.append(meta)
            if not result.screenshot_path:
                result.screenshot_path = meta.get("path")

    def _finalise(
        self, result: ExecutionResult, plan: ExecutionPlan, executed: bool = True,
    ) -> None:
        """Post-process a result so the schema is always internally consistent."""
        if not executed:
            # No browser was launched, so Playwright is not the executor.
            result.executor = EXECUTOR_NONE
            result.steps_completed = 0
            result.coverage = 0.0
            result.metadata = dict(result.metadata or {})
            result.metadata["browser_launched"] = False
        if not result.completed_at:
            result.completed_at = _utc_now()
        if not result.status:
            result.status = STATUS_ERROR if result.error else STATUS_PASSED
        if result.status == STATUS_PASSED and result.assertions_failed:
            result.status = STATUS_FAILED
            result.error_category = FailureCategory.ASSERTION_FAILED
            result.error = f"{result.assertions_failed} assertion(s) failed"
        if result.error:
            result.error = redact_text(result.error, 1000)
        # De-duplicate screenshots and keep the first failure screenshot path.
        seen = set()
        unique_shots = []
        for shot in result.screenshots:
            path = shot.get("path")
            if path in seen:
                continue
            seen.add(path)
            unique_shots.append(shot)
        result.screenshots = unique_shots
        if result.screenshot_path is None and unique_shots:
            failure_shot = next(
                (s for s in unique_shots if str(s.get("label", "")).startswith("failure_")),
                None,
            )
            result.screenshot_path = (failure_shot or unique_shots[0]).get("path")
        result.coverage = (
            round(result.steps_completed / result.steps_total, 4) if result.steps_total else 0.0
        )
        result.metadata.setdefault("plan_status_hint", plan.status_hint)
        result.metadata.setdefault(
            "allowed_executors", list(plan.allowed_executors)
        )

    @staticmethod
    def _page_url(page: Any) -> Optional[str]:
        try:
            url = str(getattr(page, "url", "") or "")
            return redact_url(url) if url else None
        except Exception:
            return None


__all__ = ["PlaywrightTestExecutor", "PLAYWRIGHT_AVAILABLE"]
