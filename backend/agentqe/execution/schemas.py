"""
Phase 5 — Execution Schemas.

Structured, serialisable data contracts for agentic test execution:

    CandidateTest[] / RankedTest[]
            │
            ▼
      ExecutionPlan            (execution_planner.py)
            │
            ▼
      ExecutionResult          (playwright_executor.py / browser_use_executor.py)
            │
            ▼
      ExecutionRunResult       (execution_service.py)

The canonical ``ExecutionResult`` lives in :mod:`agentqe.models.execution` so
that existing imports keep working; it is re-exported here.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentqe.models.execution import ExecutionResult  # noqa: F401  (re-export)


# ── Statuses ─────────────────────────────────────────────────────────────────
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
STATUS_UNSUPPORTED = "unsupported"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"

ALL_STATUSES = (
    STATUS_PASSED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_BLOCKED,
    STATUS_UNSUPPORTED,
    STATUS_TIMEOUT,
    STATUS_ERROR,
)

#: Statuses that count as a successful terminal outcome.
TERMINAL_STATUSES = (STATUS_PASSED, STATUS_FAILED, STATUS_SKIPPED,
                     STATUS_BLOCKED, STATUS_UNSUPPORTED, STATUS_TIMEOUT, STATUS_ERROR)

#: Statuses where the executor actually drove a browser.
EXECUTED_STATUSES = (STATUS_PASSED, STATUS_FAILED, STATUS_TIMEOUT, STATUS_ERROR)


# ── Failure categories (Phase 17) ───────────────────────────────────────────
class FailureCategory:
    """
    Structural classification of execution failures.

    Phase 5 collects and classifies failures. It deliberately performs *no*
    root-cause analysis — that is Phase 6's job.
    """

    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_NOT_INTERACTABLE = "ELEMENT_NOT_INTERACTABLE"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    BROWSER_ERROR = "BROWSER_ERROR"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    MISSING_TEST_DATA = "MISSING_TEST_DATA"
    EXECUTOR_ERROR = "EXECUTOR_ERROR"

    ALL = (
        ELEMENT_NOT_FOUND,
        ELEMENT_NOT_INTERACTABLE,
        NAVIGATION_ERROR,
        ASSERTION_FAILED,
        TIMEOUT,
        NETWORK_ERROR,
        BROWSER_ERROR,
        UNSUPPORTED_ACTION,
        MISSING_TEST_DATA,
        EXECUTOR_ERROR,
    )


# ── Executors ───────────────────────────────────────────────────────────────
EXECUTOR_PLAYWRIGHT = "playwright"
EXECUTOR_BROWSER_USE = "browser_use"
EXECUTOR_HYBRID = "hybrid"
EXECUTOR_NONE = "none"

ALL_EXECUTORS = (EXECUTOR_PLAYWRIGHT, EXECUTOR_BROWSER_USE, EXECUTOR_HYBRID, EXECUTOR_NONE)


# ── Actions ─────────────────────────────────────────────────────────────────
class ActionType:
    """Deterministic actions the Playwright executor understands."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    HOVER = "hover"
    SUBMIT = "submit"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    ASSERT_URL = "assert_url"
    ASSERT_TEXT = "assert_text"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_NOT_VISIBLE = "assert_not_visible"
    ASSERT_ELEMENT_EXISTS = "assert_element_exists"
    ASSERT_ELEMENT_ABSENT = "assert_element_absent"

    ALL = (
        NAVIGATE, CLICK, FILL, SELECT, CHECK, UNCHECK, PRESS, HOVER, SUBMIT,
        WAIT, SCREENSHOT, ASSERT_URL, ASSERT_TEXT, ASSERT_VISIBLE,
        ASSERT_NOT_VISIBLE, ASSERT_ELEMENT_EXISTS, ASSERT_ELEMENT_ABSENT,
    )

    #: Actions that evaluate an expectation rather than drive the UI.
    ASSERTIONS = (
        ASSERT_URL, ASSERT_TEXT, ASSERT_VISIBLE, ASSERT_NOT_VISIBLE,
        ASSERT_ELEMENT_EXISTS, ASSERT_ELEMENT_ABSENT,
    )

    #: Actions that need a resolved element locator.
    REQUIRE_TARGET = (
        CLICK, FILL, SELECT, CHECK, UNCHECK, PRESS, HOVER,
        ASSERT_VISIBLE, ASSERT_NOT_VISIBLE,
        ASSERT_ELEMENT_EXISTS, ASSERT_ELEMENT_ABSENT,
    )


#: Selector strategies, ordered by robustness (Part 5).
SELECTOR_STRATEGY_ORDER = (
    "role_name",      # accessibility role + accessible name
    "test_id",        # stable test identifier (data-testid / data-test / data-test-id)
    "label",          # associated <label>
    "attribute",      # stable attribute (id / name / aria-label / placeholder)
    "css",            # observed CSS selector built from observed identifiers
    "xpath",          # observed XPath — last resort only
)


@dataclass
class SelectorCandidate:
    """One way of locating an element, with the strategy that produced it."""

    strategy: str
    value: str
    role: Optional[str] = None
    name: Optional[str] = None
    strict: bool = True
    source: str = ""          # provenance: control id, element index, ...
    observation_status: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "value": self.value,
            "role": self.role,
            "name": self.name,
            "strict": self.strict,
            "source": self.source,
            "observation_status": self.observation_status,
        }


@dataclass
class ExecutionStepPlan:
    """
    One deterministic step of an execution plan.

    A step is either *supported* (the executor knows how to run it and has
    enough information) or explicitly ``unsupported`` with a reason. Plans
    never fabricate application behaviour.
    """

    index: int
    action: str
    target: str = ""
    value: Any = None
    description: str = ""
    source_text: str = ""
    selectors: List[SelectorCandidate] = field(default_factory=list)
    expected: Optional[str] = None
    timeout_ms: Optional[int] = None
    optional: bool = False
    supported: bool = True
    unsupported_reason: str = ""
    unsupported_category: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "description": self.description,
            "source_text": self.source_text,
            "selectors": [s.to_dict() for s in self.selectors],
            "expected": self.expected,
            "timeout_ms": self.timeout_ms,
            "optional": self.optional,
            "supported": self.supported,
            "unsupported_reason": self.unsupported_reason,
            "unsupported_category": self.unsupported_category,
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionPlan:
    """
    A CandidateTest translated into something an executor can actually run.

    ``status_hint`` is one of ``ready`` / ``blocked`` / ``unsupported`` and
    explains, without running anything, whether this plan is executable.
    """

    test_id: str
    title: str = ""
    target_url: str = ""
    layer: str = "ui"
    test_type: str = "UI"
    steps: List[ExecutionStepPlan] = field(default_factory=list)
    expected_outcomes: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    status_hint: str = "ready"
    blocked_reason: str = ""
    unsupported_reason: str = ""
    allowed_executors: List[str] = field(default_factory=lambda: [EXECUTOR_PLAYWRIGHT])
    selectors: List[SelectorCandidate] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def supported_steps(self) -> List[ExecutionStepPlan]:
        return [s for s in self.steps if s.supported]

    @property
    def unsupported_steps(self) -> List[ExecutionStepPlan]:
        return [s for s in self.steps if not s.supported]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "target_url": self.target_url,
            "layer": self.layer,
            "test_type": self.test_type,
            "status_hint": self.status_hint,
            "blocked_reason": self.blocked_reason,
            "unsupported_reason": self.unsupported_reason,
            "allowed_executors": list(self.allowed_executors),
            "steps": [s.to_dict() for s in self.steps],
            "steps_total": len(self.steps),
            "steps_supported": len(self.supported_steps),
            "steps_unsupported": len(self.unsupported_steps),
            "expected_outcomes": list(self.expected_outcomes),
            "preconditions": list(self.preconditions),
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }


@dataclass
class AssertionResult:
    """Outcome of a single expectation check."""

    index: int
    assertion_type: str
    passed: bool
    expected: str = ""
    actual: str = ""
    message: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "assertion_type": self.assertion_type,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class StepResult:
    """Structured outcome for one executed step."""

    index: int
    action: str
    status: str = STATUS_PASSED
    target: str = ""
    description: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    selector_used: Optional[str] = None
    selector_strategy: Optional[str] = None
    error: Optional[str] = None
    error_category: Optional[str] = None
    screenshot_path: Optional[str] = None
    assertion: Optional[AssertionResult] = None
    page_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "action": self.action,
            "status": self.status,
            "target": self.target,
            "description": self.description,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "selector_used": self.selector_used,
            "selector_strategy": self.selector_strategy,
            "error": self.error,
            "error_category": self.error_category,
            "screenshot_path": self.screenshot_path,
            "assertion": self.assertion.to_dict() if self.assertion else None,
            "page_url": self.page_url,
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionArtifact:
    """
    A file or logical artifact produced by an execution.

    Only *paths and references* are persisted — never base64 blobs.
    """

    artifact_type: str          # screenshot | trace | console | network | report
    path: Optional[str] = None
    label: str = ""
    step_index: Optional[int] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "path": self.path,
            "label": self.label,
            "step_index": self.step_index,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "url": self.url,
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionSummary:
    """Aggregate counts for a batch of executions (dashboard summary)."""

    total: int = 0
    executed: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    unsupported: int = 0
    skipped: int = 0
    timeout: int = 0
    error: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "executed": self.executed,
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "unsupported": self.unsupported,
            "skipped": self.skipped,
            "timeout": self.timeout,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ExecutionRunResult:
    """The result of executing a batch (RankedTest[] → ExecutionResult[])."""

    execution_run_id: str
    summary: ExecutionSummary
    results: List[ExecutionResult] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    persisted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_run_id": self.execution_run_id,
            "summary": self.summary.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "persisted": self.persisted,
            "metadata": dict(self.metadata),
        }


__all__ = [
    "STATUS_PASSED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_BLOCKED",
    "STATUS_UNSUPPORTED", "STATUS_TIMEOUT", "STATUS_ERROR", "ALL_STATUSES",
    "TERMINAL_STATUSES", "EXECUTED_STATUSES",
    "FailureCategory", "ActionType", "SELECTOR_STRATEGY_ORDER",
    "EXECUTOR_PLAYWRIGHT", "EXECUTOR_BROWSER_USE", "EXECUTOR_HYBRID", "EXECUTOR_NONE",
    "ALL_EXECUTORS",
    "SelectorCandidate", "ExecutionStepPlan", "ExecutionPlan",
    "AssertionResult", "StepResult", "ExecutionArtifact",
    "ExecutionSummary", "ExecutionRunResult", "ExecutionResult",
]
