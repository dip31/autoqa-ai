"""
Phase 5 — ExecutionService (batch orchestrator).

Ties the pipeline together:

    RankedTest[] / CandidateTest[]
            │
            ▼
    ExecutionPlanner            → ExecutionPlan per test
            │
            ▼
    PlaywrightTestExecutor      → ExecutionResult  (primary, deterministic)
            │
            ▼ (optional, opt-in, only for configured failures)
    BrowserUseTestExecutor      → ExecutionResult  (agentic recovery)
            │
            ▼
    ExecutionRepository         → agentqe_execution* tables

Guarantees:

* Tests run in **rank order** (highest priority first), sequentially by default.
* Every test is **isolated**: one browser context per test, fresh page state.
* A single test crashing never aborts the batch; it is recorded as ``error``.
* No test data beyond the configured synthetic credentials is ever used.
* Phase 5 records what happened. It performs no root-cause analysis.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.interfaces import (
    IBrowserAgentExecutor,
    IExecutionRepository,
    IEvidenceCollector,
    ITestExecutor,
)
from agentqe.execution.redaction import redact_text, redact_url
from agentqe.execution.schemas import (
    EXECUTOR_NONE,
    EXECUTOR_PLAYWRIGHT,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRunResult,
    ExecutionSummary,
    FailureCategory,
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_SKIPPED,
    STATUS_UNSUPPORTED,
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionService:
    """
    Executes a batch of ranked tests in priority order.

    All collaborators are injectable so the service can be unit-tested without
    Playwright, a database, or a real browser.
    """

    def __init__(
        self,
        planner: Any = None,
        executor: Optional[ITestExecutor] = None,
        browser_agent: Optional[IBrowserAgentExecutor] = None,
        repository: Optional[IExecutionRepository] = None,
        evidence: Optional[IEvidenceCollector] = None,
        config: Optional[ExecutionConfig] = None,
    ):
        self.config = config or get_execution_config()
        self.planner = planner or self._default_planner()
        self.executor = executor or self._default_executor()
        self.browser_agent = browser_agent
        self.repository = repository
        self.evidence = evidence
        #: Per-test plan cache, exposed for the API layer / debugging.
        self.plans: Dict[str, ExecutionPlan] = {}

    # ── Defaults ────────────────────────────────────────────────────────
    def _default_planner(self) -> Any:
        from agentqe.execution.execution_planner import ExecutionPlanner
        return ExecutionPlanner(self.config)

    def _default_executor(self) -> ITestExecutor:
        from agentqe.execution.playwright_executor import PlaywrightTestExecutor
        return PlaywrightTestExecutor(self.config)

    def _default_browser_agent(self) -> IBrowserAgentExecutor:
        from agentqe.execution.browser_use_executor import build_browser_agent_executor
        return build_browser_agent_executor(self.config)

    # ── Public API ──────────────────────────────────────────────────────
    def execute_tests(
        self,
        tests: Iterable[Any],
        base_url: Optional[str] = None,
        application_context: Optional[ApplicationContext] = None,
        context: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> ExecutionRunResult:
        """
        Execute ``tests`` (RankedTest[] or CandidateTest[]) in rank order.

        ``base_url`` overrides the URL recorded on each plan, which is what the
        API layer uses to point tests at a live local application.
        """
        ranked = self._normalise(tests)
        run_id = f"execrun_{uuid.uuid4().hex[:16]}"
        started_at = _utc_now()
        wall_start = time.time()

        ctx = dict(context or {})
        ctx["execution_run_id"] = run_id
        if base_url:
            ctx["base_url"] = base_url

        results: List[ExecutionResult] = []
        summary = ExecutionSummary()
        self.plans = {}

        for position, (test, ranking) in enumerate(ranked, start=1):
            result = self._execute_one(
                test,
                ranking,
                position=position,
                base_url=base_url,
                application_context=application_context,
                context=ctx,
            )
            results.append(result)
            self._accumulate(summary, result)

        summary.duration_ms = round((time.time() - wall_start) * 1000.0, 2)

        run_result = ExecutionRunResult(
            execution_run_id=run_id,
            summary=summary,
            results=results,
            started_at=started_at,
            completed_at=_utc_now(),
            metadata={
                "run": {
                    "base_url": redact_url(base_url) if base_url else None,
                    "concurrency": self.config.effective_concurrency(),
                    "browser_use_enabled": self.config.browser_use_enabled,
                    "executor": EXECUTOR_PLAYWRIGHT,
                },
                "config": self.config.to_dict(),
                "ranking": [r.get("ranking_mode") for _, r in ranked],
                "plans": {tid: plan.to_dict() for tid, plan in self.plans.items()},
            },
        )

        if persist and self.repository is not None:
            try:
                self.repository.save_run_result(run_result, context=ctx, plans=self.plans)
            except Exception as exc:
                logger.warning("[ExecutionService] persistence failed: %s", exc)
                run_result.persisted = False

        return run_result

    def execute_test(
        self,
        test: Any,
        base_url: Optional[str] = None,
        application_context: Optional[ApplicationContext] = None,
        context: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> ExecutionResult:
        """Execute a single test (used by the single-test API route)."""
        run = self.execute_tests(
            [test],
            base_url=base_url,
            application_context=application_context,
            context=context,
            persist=persist,
        )
        return run.results[0] if run.results else ExecutionResult(
            test_id=getattr(test, "test_id", "unknown"),
            status=STATUS_ERROR,
            executor=EXECUTOR_NONE,
            error="execution produced no result",
            error_category=FailureCategory.EXECUTOR_ERROR,
        )

    # ── Per-test flow ───────────────────────────────────────────────────
    def _execute_one(
        self,
        test: CandidateTest,
        ranking: Dict[str, Any],
        position: int,
        base_url: Optional[str],
        application_context: Optional[ApplicationContext],
        context: Dict[str, Any],
    ) -> ExecutionResult:
        test_id = getattr(test, "test_id", "") or "unknown"
        plan: Optional[ExecutionPlan] = None
        try:
            plan = self.planner.plan(
                test, application_context, base_url=base_url,
                rank_position=position,
            )
            self.plans[test_id] = plan
        except Exception as exc:
            logger.warning("[ExecutionService] could not plan %s: %s", test_id, exc)
            return self._attach_ranking(
                self._non_runnable(
                    test_id, STATUS_ERROR,
                    f"could not build an execution plan: {redact_text(exc, 300)}",
                    FailureCategory.EXECUTOR_ERROR,
                ),
                ranking, position,
            )

        if plan.status_hint == "unsupported":
            return self._attach_ranking(
                self._non_runnable(
                    test_id, STATUS_UNSUPPORTED,
                    plan.unsupported_reason or "no supported action could be planned",
                    FailureCategory.UNSUPPORTED_ACTION,
                    plan=plan,
                ),
                ranking, position,
            )
        if plan.status_hint == "blocked":
            return self._attach_ranking(
                self._non_runnable(
                    test_id, STATUS_BLOCKED,
                    plan.blocked_reason or "the plan is blocked: missing required information",
                    FailureCategory.MISSING_TEST_DATA,
                    plan=plan,
                ),
                ranking, position,
            )
        if plan.status_hint == "skipped":
            return self._attach_ranking(
                self._non_runnable(
                    test_id, STATUS_SKIPPED,
                    plan.unsupported_reason or "the test was skipped",
                    FailureCategory.UNSUPPORTED_ACTION,
                    plan=plan,
                ),
                ranking, position,
            )

        result = self._run(plan, test, application_context)
        result = self._maybe_agentic(plan, test, application_context, result)
        return self._attach_ranking(result, ranking, position, plan=plan)

    def _run(
        self,
        plan: ExecutionPlan,
        test: CandidateTest,
        application_context: Optional[ApplicationContext],
    ) -> ExecutionResult:
        """Primary deterministic execution. Never raises."""
        try:
            result = self.executor.execute_plan(
                plan, test=test, application_context=application_context, config=self.config
            )
        except Exception as exc:
            logger.exception("[ExecutionService] executor crashed for %s", plan.test_id)
            return self._non_runnable(
                plan.test_id, STATUS_ERROR,
                redact_text(f"executor error: {exc}", 500),
                FailureCategory.EXECUTOR_ERROR,
                plan=plan,
            )

        result.metadata = dict(result.metadata or {})
        result.metadata.setdefault("test_title", plan.title)
        result.metadata.setdefault("layer", plan.layer)
        result.metadata.setdefault("steps_total", plan.to_dict()["steps_total"])
        result.metadata.setdefault("steps_unsupported", len(plan.unsupported_steps))
        if plan.unsupported_steps:
            result.metadata["unsupported_steps"] = [
                {
                    "index": s.index,
                    "source_text": s.source_text,
                    "reason": s.unsupported_reason,
                }
                for s in plan.unsupported_steps
            ]
        result.evidence_refs = list(result.evidence_refs) or list(plan.evidence_refs)
        return result

    def _maybe_agentic(
        self,
        plan: ExecutionPlan,
        test: CandidateTest,
        application_context: Optional[ApplicationContext],
        result: ExecutionResult,
    ) -> ExecutionResult:
        """
        Optional agentic recovery.

        The rules that make this safe:
          * the config gate is checked *first* — while Browser Use is disabled
            the agent is never even asked whether it could help,
          * never for a passing test,
          * never unless Browser Use is enabled AND configured,
          * never unless the failure category is explicitly whitelisted,
          * otherwise the deterministic result is returned untouched.
        """
        if not self.config.browser_use_enabled:
            return result
        if not self.config.browser_use_fallback_enabled:
            return result

        agent = self.browser_agent or self._default_browser_agent()
        if agent is None:
            return result

        can_recover = getattr(agent, "can_recover", None)
        if not callable(can_recover) or not can_recover(result):
            return result
        logger.info(
            "[ExecutionService] attempting agentic recovery for %s (%s)",
            plan.test_id, result.error_category,
        )
        try:
            recovered, was_recovered = agent.recover(
                plan, result, test=test,
                application_context=application_context,
                config=self.config,
            )
        except Exception as exc:
            logger.warning("[ExecutionService] agentic recovery errored: %s", exc)
            result.metadata = dict(result.metadata or {})
            result.metadata["browser_use_error"] = redact_text(exc, 300)
            return result

        if not was_recovered:
            return recovered
        recovered.metadata = dict(recovered.metadata or {})
        recovered.metadata["recovered"] = True
        recovered.metadata["deterministic_status"] = result.status
        return recovered

    # ── Helpers ─────────────────────────────────────────────────────────
    def _normalise(
        self, tests: Iterable[Any]
    ) -> List[Tuple[CandidateTest, Dict[str, Any]]]:
        """
        Accept RankedTest[], CandidateTest[], or dicts and return
        ``[(test, ranking_metadata), ...]`` in rank order.
        """
        items: List[Tuple[CandidateTest, Dict[str, Any]]] = []
        for index, entry in enumerate(tests or [], start=1):
            test, ranking = self._split(entry, index)
            if test is None:
                continue
            items.append((test, ranking))
        items.sort(key=lambda pair: pair[1].get("__order", 0))
        return items

    @staticmethod
    def _split(entry: Any, index: int) -> Tuple[Optional[CandidateTest], Dict[str, Any]]:
        """Unwrap a RankedTest / dict / CandidateTest into (test, ranking)."""
        if entry is None:
            return None, {}

        # RankedTest / PrioritizedTest dataclass
        if hasattr(entry, "test") and not isinstance(entry, dict):
            inner = getattr(entry, "test")
            if isinstance(inner, dict):
                return _as_candidate_test(inner), _ranking_from_object(entry, index)
            if inner is not None:
                return inner, _ranking_from_object(entry, index)

        if isinstance(entry, dict):
            if "test" in entry and isinstance(entry["test"], dict):
                return _as_candidate_test(entry["test"]), _ranking_from_mapping(entry, index)
            return _as_candidate_test(entry), _ranking_from_mapping(entry, index)

        # Plain CandidateTest
        if hasattr(entry, "test_id"):
            return entry, _ranking_from_object(entry, index)

        return None, {}

    @staticmethod
    def _accumulate(summary: ExecutionSummary, result: ExecutionResult) -> None:
        summary.total += 1
        status = result.status
        if status in ("passed", "failed", "timeout", "error"):
            summary.executed += 1
        if hasattr(summary, status):
            setattr(summary, status, getattr(summary, status) + 1)

    def _non_runnable(
        self,
        test_id: str,
        status: str,
        message: str,
        category: str,
        plan: Optional[ExecutionPlan] = None,
    ) -> ExecutionResult:
        now = _utc_now()
        return ExecutionResult(
            test_id=test_id,
            status=status,
            executor=EXECUTOR_NONE,
            error=redact_text(message, 500),
            error_category=category,
            started_at=now,
            completed_at=now,
            steps_total=len(plan.steps) if plan else 0,
            steps_completed=0,
            metadata={
                "test_title": plan.title if plan else None,
                "layer": plan.layer if plan else "ui",
                "not_executed": True,
            },
        )

    @staticmethod
    def _attach_ranking(
        result: ExecutionResult,
        ranking: Dict[str, Any],
        position: int,
        plan: Optional[ExecutionPlan] = None,
    ) -> ExecutionResult:
        """Copy Phase 4 provenance onto the result (no data invented)."""
        result.rank_position = ranking.get("__order", position)
        result.priority_score = ranking.get("__order_score", result.priority_score)
        result.predicted_priority = ranking.get("__predicted_priority")
        result.ranking_mode = ranking.get("ranking_mode")
        result.model_status = ranking.get("model_status")
        result.model_version = ranking.get("model_version")
        result.feature_version = ranking.get("feature_version")
        result.features = dict(ranking.get("features") or {})
        result.feature_contributions = dict(ranking.get("feature_contributions") or {})
        result.metadata = dict(result.metadata or {})
        result.metadata.setdefault(
            "heuristic_priority", ranking.get("__heuristic_priority")
        )
        result.metadata.setdefault(
            "heuristic_score", ranking.get("__heuristic_score")
        )
        result.metadata.setdefault("rank_position", result.rank_position)
        return result


# ── ranking unwrapping helpers ──────────────────────────────────────────────
def _ranking_from_object(entry: Any, index: int) -> Dict[str, Any]:
    """Build the ranking map from a RankedTest-like object.

    Mirrors _ranking_from_mapping: accepts Phase 4 attributes
    (bootstrap_score, feature_vector) and generic ones.
    """
    features = _as_float_dict(getattr(entry, "features", None))
    if not features:
        features = _as_float_dict(getattr(entry, "feature_vector", None))
    contributions = _as_float_dict(getattr(entry, "feature_contributions", None))
    score = _first_not_none(
        getattr(entry, "score", None),
        getattr(entry, "final_score", None),
        getattr(entry, "total_score", None),
        getattr(entry, "bootstrap_score", None),
        getattr(entry, "priority_score", None),
    )
    return {
        "__order": index,
        "__order_score": _as_float(score),
        "__predicted_priority": _as_float(
            getattr(entry, "predicted_priority", None)
        ),
        "ranking_mode": getattr(entry, "ranking_mode", None),
        "model_status": getattr(entry, "model_status", None),
        "model_version": getattr(entry, "model_version", None),
        "feature_version": getattr(entry, "feature_version", None) or _feature_version(features),
        "features": features,
        "feature_contributions": contributions,
    }


def _ranking_from_mapping(entry: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Build the ranking map from a serialised RankedTest dict.

    Accepts both the Phase 4 ``RankedTest.to_dict()`` shape (``bootstrap_score``
    / ``feature_vector``) and the generic ML shapes (``final_score`` / ``score``
    / ``features``) so no provenance is silently dropped.
    """
    score = _first_not_none(
        entry.get("final_score"),
        entry.get("score"),
        entry.get("total_score"),
        entry.get("bootstrap_score"),
        entry.get("priority_score"),
    )
    features = entry.get("features")
    if not isinstance(features, dict):
        features = entry.get("feature_vector")
    return {
        "__order": index,
        "__order_score": _as_float(score),
        "__predicted_priority": _as_float(entry.get("predicted_priority")),
        "ranking_mode": entry.get("ranking_mode"),
        "model_status": entry.get("model_status"),
        "model_version": entry.get("model_version"),
        "feature_version": entry.get("feature_version") or _feature_version(features),
        "features": _as_float_dict(features),
        "feature_contributions": _as_float_dict(entry.get("feature_contributions")),
    }


def _feature_version(features: Any) -> Optional[str]:
    if isinstance(features, dict):
        version = features.get("version") or features.get("feature_version")
        if version:
            return str(version)
    return None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float_dict(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, float] = {}
    for key, val in value.items():
        fval = _as_float(val)
        if fval is not None:
            out[str(key)] = fval
    return out


def _as_candidate_test(data: Dict[str, Any]) -> Optional[CandidateTest]:
    """Best-effort dict → CandidateTest (tolerates missing optional fields)."""
    try:
        known = {f for f in getattr(CandidateTest, "__dataclass_fields__", {})}
        payload = {k: v for k, v in data.items() if k in known}
        if not payload.get("test_id"):
            return None
        return CandidateTest(**payload)
    except Exception:
        return None


__all__ = ["ExecutionService"]
