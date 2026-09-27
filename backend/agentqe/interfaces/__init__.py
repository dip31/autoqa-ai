"""
AgentQE Capability Interfaces

Defines contracts between future capabilities.
Implementations belong in agents/, enrichment/, execution/, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from agentqe.models.context import ApplicationContext, ApplicationUnderstandingInput


@dataclass
class CandidateTest:
    test_id: str
    title: str
    description: str = ""
    perspective: str = "USER"
    test_type: str = "UI"
    target: str = ""
    priority: str = "Medium"
    category: str = ""
    steps: List = field(default_factory=list)
    input_data: str = ""
    expected_result: str = ""
    automatable: bool = True
    blocked_reason: Optional[str] = None
    source_agent: str = ""
    metadata: Dict = field(default_factory=dict)
    risk_score: float = 0.5
    historical_pass_rate: float = 0.0
    historical_failure_rate: float = 0.0
    execution_cost: float = 3.0
    change_impact: float = 0.5
    coverage_gain: float = 0.5
    transformer_score: float = 0.0
    final_score: float = 0.0


@dataclass
class ExecutionResult:
    test_id: str
    status: str
    duration_ms: float = 0.0
    error: Optional[str] = None
    coverage: float = 0.0
    healed: bool = False
    screenshot_path: Optional[str] = None
    security_findings: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    finding_id: str
    category: str
    severity: str
    description: str
    evidence: Dict = field(default_factory=dict)
    source: str = ""
    status: str = "OPEN"


@dataclass
class Risk:
    risk_id: str
    area: str
    severity: str
    score: float
    reason: str
    evidence: List[str] = field(default_factory=list)
    affected_tests: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Capability Contracts
# ──────────────────────────────────────────────────────────────────────────────

class IApplicationUnderstanding(ABC):
    """Application Understanding → ApplicationContext"""

    @abstractmethod
    def analyze(self, input_data: ApplicationUnderstandingInput) -> ApplicationContext:
        """Analyze application and return structured context."""
        pass


class ITestGenerator(ABC):
    """Test Generation → List[CandidateTest]"""

    @abstractmethod
    def generate(self, context: ApplicationContext, strategy: Dict[str, Any]) -> List[CandidateTest]:
        """Generate test cases from context and strategy."""
        pass


class IPrioritizer(ABC):
    """Prioritization → Prioritized CandidateTest[]"""

    @abstractmethod
    def rank(self, candidates: List[CandidateTest], context: ApplicationContext) -> List[CandidateTest]:
        """Score and rank all candidates."""
        pass

    @abstractmethod
    def select(self, ranked: List[CandidateTest], budget: int) -> List[CandidateTest]:
        """Select top-k tests within execution budget."""
        pass


class ITestExecutor(ABC):
    """Execution → List[ExecutionResult]"""

    @abstractmethod
    def execute(self, tests: List[CandidateTest], context: ApplicationContext) -> List[ExecutionResult]:
        """Execute selected tests and return results."""
        pass


class IFailureAnalyzer(ABC):
    """Failure Analysis → List[Finding]"""

    @abstractmethod
    def analyze(self, results: List[ExecutionResult], context: ApplicationContext) -> List[Finding]:
        """Analyze execution failures and produce findings."""
        pass


class ISecurityValidator(ABC):
    """Security Validation → List[Finding]"""

    @abstractmethod
    def validate(self, context: ApplicationContext, tests: List[CandidateTest]) -> List[Finding]:
        """Run security validation and produce findings."""
        pass


class IRiskAssessor(ABC):
    """Risk Assessment → List[Risk]"""

    @abstractmethod
    def assess(self, context: ApplicationContext, results: List[ExecutionResult], findings: List[Finding]) -> List[Risk]:
        """Assess deployment risk based on execution and findings."""
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Registry for Dependency Injection (Phase 1+)
# ──────────────────────────────────────────────────────────────────────────────

class CapabilityRegistry:
    """Registry for capability implementations. Phase 1+ will populate this."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._implementations = {}
        return cls._instance

    def register(self, interface: type, implementation: type):
        self._implementations[interface] = implementation

    def get(self, interface: type):
        return self._implementations.get(interface)

    def resolve(self, interface: type):
        impl = self.get(interface)
        if impl is None:
            raise ValueError(f"No implementation registered for {interface.__name__}")
        return impl()


registry = CapabilityRegistry()