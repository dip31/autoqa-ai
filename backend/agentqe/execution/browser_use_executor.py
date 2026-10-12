"""
Phase 5 — Browser Use Adapter (OPTIONAL AGENTIC EXECUTOR).

Browser Use is a *secondary*, opt-in capability. It is never required for
Phase 5, and it is never invoked for every test.

Invocation policy — the adapter refuses unless ALL of these hold:

1. ``AGENTQE_BROWSER_USE_ENABLED=true`` (off by default),
2. the ``browser_use`` package is importable,
3. the plan explicitly allows the agentic executor, and
4. either (a) recovery was requested and the failure category is in
   ``browser_use_fallback_categories``, or (b) a step is explicitly marked as
   requiring dynamic/semantic reasoning.

If any condition fails, :meth:`BrowserUseTestExecutor.is_available` is False and
:meth:`execute_plan` returns the deterministic result untouched with a note
explaining why. That is the "fall back to Playwright-only behaviour" rule.

Nothing outside this module imports Browser Use.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.interfaces import IBrowserAgentExecutor
from agentqe.execution.redaction import redact_text, redact_url
from agentqe.execution.schemas import (
    ActionType,
    EXECUTOR_BROWSER_USE,
    EXECUTOR_HYBRID,
    EXECUTOR_NONE,
    EXECUTOR_PLAYWRIGHT,
    ExecutionPlan,
    ExecutionResult,
    FailureCategory,
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_UNSUPPORTED,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from browser_use import Agent as _BrowserUseAgent
    from browser_use import Browser as _BrowserUseBrowser
    from browser_use import BrowserConfig as _BrowserUseBrowserConfig
    BROWSER_USE_AVAILABLE = True
except Exception:  # pragma: no cover
    _BrowserUseAgent = None
    _BrowserUseBrowser = None
    _BrowserUseBrowserConfig = None
    BROWSER_USE_AVAILABLE = False


class BrowserUseTestExecutor(IBrowserAgentExecutor):
    """
    Thin adapter around the Browser Use library.

    The adapter's contract with the rest of AgentQE is deliberately narrow: it
    takes a plan plus the deterministic result, and returns either a recovered
    result or a structured non-recovery result. It never silently replaces
    Playwright.
    """

    name = EXECUTOR_BROWSER_USE

    def __init__(self, config: Optional[ExecutionConfig] = None, agent_factory: Any = None):
        self.config = config or get_execution_config()
        #: Injection point for tests / alternative backends.
        self._agent_factory = agent_factory

    # ── Availability ───────────────────────────────────────────────────
    @property
    def is_available(self) -> bool:
        if not self.config.browser_use_enabled:
            return False
        if self._agent_factory is not None:
            return True
        if not BROWSER_USE_AVAILABLE:
            return False
        # A configured API key is required by the real library; when a local
        # model is configured the key check is relaxed.
        if not os.getenv("BROWSER_USE_API_KEY") and not os.getenv("OPENAI_API_KEY") \
                and not os.getenv("BROWSER_USE_USE_LOCAL"):
            return False
        return True

    def unavailable_reason(self) -> Optional[str]:
        if self.is_available:
            return None
        if not self.config.browser_use_enabled:
            return (
                "Browser Use is disabled (set AGENTQE_BROWSER_USE_ENABLED=true to enable "
                "the optional agentic executor)"
            )
        if self._agent_factory is None and not BROWSER_USE_AVAILABLE:
            return "the 'browser_use' package is not installed in this environment"
        return (
            "Browser Use is installed but not configured (set BROWSER_USE_API_KEY or "
            "BROWSER_USE_USE_LOCAL=true)"
        )

    def can_recover(self, result: ExecutionResult) -> bool:
        """Only recover from the configured categories, and only if enabled."""
        if not self.is_available:
            return False
        if not self.config.browser_use_fallback_enabled:
            return False
        if result is None or result.status in ("passed",):
            return False
        category = result.error_category
        if category not in self.config.browser_use_fallback_categories:
            return False
        return True

    # ── ITestExecutor surface ──────────────────────────────────────────
    def execute(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext] = None,
        plan: Optional[ExecutionPlan] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
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
        """
        Attempt an agentic run of ``plan``.

        Returns a structured ``unsupported`` result when the adapter is not
        permitted to run — the caller then keeps the deterministic result.
        """
        cfg = config or self.config
        reason = self._refusal_reason(plan)
        if reason:
            return self._refuse(plan, reason, cfg)

        task = self._build_task(plan)
        try:
            agent = self._build_agent(cfg)
        except Exception as exc:
            return self._refuse(
                plan, f"could not initialise the agentic executor: {redact_text(exc, 200)}", cfg
            )

        started = _utc_now()
        try:
            history = agent.run(task=task, max_steps=cfg.browser_use_max_steps)
        except TypeError:
            # Older/newer signatures.
            history = agent.run(task)
        except Exception as exc:
            result = ExecutionResult(
                test_id=plan.test_id, status=STATUS_ERROR, executor=self.name,
                error=redact_text(f"agentic execution failed: {exc}", 500),
                error_category=FailureCategory.EXECUTOR_ERROR,
                started_at=started, completed_at=_utc_now(),
            )
            return result

        return self._to_result(plan, history, started)

    # ── Recovery entry point (used by ExecutionService) ───────────────
    def recover(
        self,
        plan: ExecutionPlan,
        deterministic_result: ExecutionResult,
        test: Optional[CandidateTest] = None,
        application_context: Optional[ApplicationContext] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> Tuple[ExecutionResult, bool]:
        """
        Attempt recovery of a failed deterministic execution.

        Returns ``(result, recovered)``. When recovery is not permitted, the
        deterministic result is returned unchanged with
        ``executor='hybrid'`` and a note, so the caller can report the original
        failure faithfully.
        """
        cfg = config or self.config
        if not self.can_recover(deterministic_result):
            reason = self.unavailable_reason() or (
                f"failure category '{deterministic_result.error_category}' is not in the "
                f"configured agentic fallback set {list(cfg.browser_use_fallback_categories)}"
            )
            noted = deterministic_result
            noted.executor = EXECUTOR_HYBRID if self.config.browser_use_enabled else EXECUTOR_NONE
            noted.metadata = dict(noted.metadata or {})
            noted.metadata["browser_use_skipped"] = redact_text(reason, 300)
            return noted, False

        agentic = self.execute_plan(
            plan, test=test, application_context=application_context, config=cfg
        )
        agentic.executor = EXECUTOR_HYBRID
        agentic.metadata = dict(agentic.metadata or {})
        agentic.metadata["recovered_from_executor"] = EXECUTOR_PLAYWRIGHT
        agentic.metadata["recovered_from_status"] = deterministic_result.status
        agentic.metadata["recovered_from_category"] = deterministic_result.error_category
        if agentic.status in ("passed", "failed", "timeout"):
            return agentic, True
        # The agentic attempt added nothing: keep the deterministic failure.
        return deterministic_result, False

    # ── Internals ──────────────────────────────────────────────────────
    def _refusal_reason(self, plan: ExecutionPlan) -> str:
        if not self.is_available:
            return self.unavailable_reason() or "agentic executor unavailable"
        if "browser_use" not in plan.allowed_executors:
            return (
                "the execution plan does not allow the agentic executor "
                "(no step required dynamic reasoning)"
            )
        if not plan.target_url:
            return "the execution plan has no target URL for an agentic run"
        return ""

    def _refuse(self, plan: ExecutionPlan, reason: str, cfg: ExecutionConfig) -> ExecutionResult:
        return ExecutionResult(
            test_id=plan.test_id,
            status=STATUS_UNSUPPORTED,
            executor=EXECUTOR_NONE,
            error=redact_text(reason, 500),
            error_category=FailureCategory.UNSUPPORTED_ACTION,
            started_at=_utc_now(), completed_at=_utc_now(),
            steps_total=len(plan.steps),
            start_url=redact_url(plan.target_url) if plan.target_url else None,
            metadata={
                "test_title": plan.title,
                "browser_use_refused": True,
                "browser_use_enabled": cfg.browser_use_enabled,
            },
        )

    def _build_task(self, plan: ExecutionPlan) -> str:
        """
        Build a bounded, deterministic task description.

        The agent is explicitly told it is a *fallback* and that unknown
        behaviour must not be invented.
        """
        lines = [
            f"Open {plan.target_url} and carry out this UI test.",
            f"Test: {plan.title or plan.test_id}",
            "Rules: do not invent behaviour; do not use real credentials; "
            "stop as soon as an expectation is unmet.",
            "Steps:",
        ]
        for step in plan.steps:
            if not step.supported:
                lines.append(f"  - (skipped, unsupported) {step.unsupported_reason}")
                continue
            value = f" with a safe test value of length {len(str(step.value))}" \
                if step.value is not None else ""
            lines.append(f"  {step.index + 1}. {step.action} '{step.target}'{value}")
        for outcome in plan.expected_outcomes[:5]:
            lines.append(f"Expected outcome: {outcome}")
        return "\n".join(lines)

    def _build_agent(self, cfg: ExecutionConfig) -> Any:
        if self._agent_factory is not None:
            return self._agent_factory()
        if not BROWSER_USE_AVAILABLE:
            raise RuntimeError("browser_use is not installed")
        browser_config = _BrowserUseBrowserConfig(headless=cfg.playwright_headless)
        return _BrowserUseAgent(task="", browser=_BrowserUseBrowser(config=browser_config))

    def _to_result(self, plan: ExecutionPlan, history: Any, started: str) -> ExecutionResult:
        """Translate a Browser Use history object into an ExecutionResult."""
        final_url = None
        success = True
        outputs: List[str] = []
        errors: List[str] = []

        try:
            result_obj = getattr(history, "final_result", None)
            if callable(result_obj):
                result_obj = result_obj()
            if result_obj is not None:
                extracted = getattr(result_obj, "extracted_content", None)
                if extracted is not None:
                    outputs.append(str(extracted)[:500])
                success = bool(getattr(result_obj, "is_success", lambda: True)())
        except Exception:
            pass

        try:
            for item in getattr(history, "history", None) or []:
                urls = getattr(getattr(item, "result", None), "extracted_content", None)
                if isinstance(urls, str) and urls.startswith("http"):
                    final_url = urls
                error_texts = getattr(item, "error", None)
                if error_texts:
                    errors.append(str(error_texts)[:300])
        except Exception:
            pass

        status = "passed" if success and not errors else "failed"
        return ExecutionResult(
            test_id=plan.test_id,
            status=status,
            executor=self.name,
            error=redact_text(errors[0], 500) if errors else None,
            error_category=FailureCategory.EXECUTOR_ERROR if errors else None,
            started_at=started, completed_at=_utc_now(),
            steps_total=len(plan.steps),
            steps_completed=len(plan.steps) if success else 0,
            start_url=redact_url(plan.target_url) if plan.target_url else None,
            final_url=redact_url(final_url) if final_url else None,
            metadata={
                "test_title": plan.title,
                "browser_use_outputs": [redact_text(o, 300) for o in outputs[:5]],
                "agentic": True,
            },
        )


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class NullBrowserAgentExecutor(IBrowserAgentExecutor):
    """
    Always-unavailable agentic executor.

    Used when ``AGENTQE_BROWSER_USE_ENABLED=false`` so callers can depend on a
    stable interface without importing Browser Use at all.
    """

    name = EXECUTOR_BROWSER_USE

    def __init__(self, config: Optional[ExecutionConfig] = None, reason: str = ""):
        self.config = config or get_execution_config()
        self._reason = reason

    @property
    def is_available(self) -> bool:
        return False

    def unavailable_reason(self) -> Optional[str]:
        return self._reason or "agentic executor disabled"

    def can_recover(self, result: ExecutionResult) -> bool:
        return False

    def execute(self, test, application_context=None, plan=None, config=None) -> ExecutionResult:
        return self.execute_plan(plan, test, application_context, config)

    def execute_plan(self, plan, test=None, application_context=None, config=None) -> ExecutionResult:
        status = STATUS_BLOCKED if plan and plan.status_hint == "blocked" else STATUS_UNSUPPORTED
        return ExecutionResult(
            test_id=(plan.test_id if plan else getattr(test, "test_id", "unknown")),
            status=status,
            executor=EXECUTOR_NONE,
            error=self.unavailable_reason(),
            error_category=FailureCategory.UNSUPPORTED_ACTION,
            started_at=_utc_now(), completed_at=_utc_now(),
        )


def build_browser_agent_executor(config: Optional[ExecutionConfig] = None) -> IBrowserAgentExecutor:
    """
    Factory: returns the real adapter when enabled, otherwise a null adapter.

    Callers can therefore always hold an :class:`IBrowserAgentExecutor` without
    guarding for the optional dependency.
    """
    cfg = config or get_execution_config()
    if not cfg.browser_use_enabled:
        return NullBrowserAgentExecutor(cfg)
    return BrowserUseTestExecutor(cfg)


__all__ = [
    "BrowserUseTestExecutor",
    "NullBrowserAgentExecutor",
    "build_browser_agent_executor",
    "BROWSER_USE_AVAILABLE",
]
