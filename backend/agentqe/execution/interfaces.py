"""
Phase 5 — Execution Interfaces.

The architectural contract that makes the executor split explicit:

    CandidateTest[] / RankedTest[]
                │
                ▼
        ExecutionPlanner        (CandidateTest  → ExecutionPlan)
                │
                ▼
        ITestExecutor           (ExecutionPlan  → ExecutionResult)
            ├── PlaywrightTestExecutor   PRIMARY / deterministic
            └── BrowserUseTestExecutor   OPTIONAL / agentic recovery
                │
                ▼
        ExecutionService        (RankedTest[]  → ExecutionRunResult)
                │
                ▼
        IExecutionRepository    (persist ExecutionRunResult)

Nothing outside this package imports Playwright or Browser Use directly, which
is what makes the engine boundary real rather than aspirational.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from agentqe.execution.config import ExecutionConfig
from agentqe.execution.schemas import ExecutionPlan, ExecutionResult


class IExecutionPlanner(ABC):
    """CandidateTest (+ ApplicationContext) → ExecutionPlan."""

    @abstractmethod
    def plan(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext] = None,
        base_url: Optional[str] = None,
        rank_position: Optional[int] = None,
    ) -> ExecutionPlan:
        """Translate a generated test into a deterministic execution plan.

        ``base_url`` overrides the application root a test runs against (used by
        the API layer to point at a live local application). ``rank_position``
        records the Phase 4 rank for provenance.

        Implementations must never fabricate application behaviour: a step whose
        required information is unknown is marked ``supported=False``.
        """


class ITestExecutor(ABC):
    """
    A single execution engine.

    Implementations MUST NOT assume the test is executable — an unexecutable
    plan yields a structured result (``unsupported`` / ``blocked`` / ``error``)
    rather than an exception escaping to the caller.
    """

    #: Stable engine identifier stored on every ExecutionResult.
    name: str = "unknown"

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this engine can run right now (dependencies installed/configured)."""

    @abstractmethod
    def execute(
        self,
        test: CandidateTest,
        application_context: Optional[ApplicationContext] = None,
        plan: Optional[ExecutionPlan] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        """Execute one test and return a fully structured result."""

    def execute_plan(
        self,
        plan: ExecutionPlan,
        test: Optional[CandidateTest] = None,
        application_context: Optional[ApplicationContext] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        """Execute a pre-built plan (used by the service and by tests)."""
        raise NotImplementedError


class IBrowserAgentExecutor(ITestExecutor):
    """
    Optional agentic browser executor (Browser Use).

    Invoked ONLY when deterministic execution is insufficient:
      * a selector could not be resolved and the plan asks for agentic help,
      * the failure category is in the configured fallback allow-list,
      * the test explicitly requires dynamic/semantic reasoning.

    Never required: when unavailable, callers must degrade to a structured
    Playwright failure (see ``BrowserUseTestExecutor.unavailable_reason``).
    """

    name = "browser_use"

    def can_recover(self, result: ExecutionResult) -> bool:
        """Whether this adapter is willing to attempt a recovery run."""
        return False

    def unavailable_reason(self) -> Optional[str]:
        """Human-readable reason the agentic executor cannot be used (else None)."""
        return None


class IEvidenceCollector(ABC):
    """Collects evidence for a single execution (screenshots, console, network)."""

    @abstractmethod
    def start(self, execution_id: str, page: Any = None) -> None: ...

    @abstractmethod
    def capture_screenshot(self, label: str, step_index: Optional[int] = None,
                           page_url: Optional[str] = None) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def finish(self, page_url: Optional[str] = None) -> Dict[str, Any]:
        """Return the collected evidence bundle (paths/refs only, no blobs)."""


class IExecutionRepository(ABC):
    """Persistence for execution history and future training data."""

    @abstractmethod
    def create_run(self, run: Dict[str, Any]) -> int: ...

    @abstractmethod
    def save_execution(
        self,
        result: ExecutionResult,
        run_id: Optional[int] = None,
        plan: Optional[ExecutionPlan] = None,
    ) -> int: ...

    @abstractmethod
    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_executions(self, **filters: Any) -> List[Dict[str, Any]]: ...


__all__ = [
    "IExecutionPlanner",
    "ITestExecutor",
    "IBrowserAgentExecutor",
    "IEvidenceCollector",
    "IExecutionRepository",
]
