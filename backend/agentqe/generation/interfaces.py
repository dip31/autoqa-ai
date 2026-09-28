from abc import ABC, abstractmethod
from typing import List, Dict, Any

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

class ITestGenerationModel(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Execute LLM generation and return text response."""
        pass

class ITestGenerator(ABC):
    @abstractmethod
    def generate(self, generation_context: Dict[str, Any]) -> List[CandidateTest]:
        """Generate test cases from built context."""
        pass

class IContextBuilder(ABC):
    @abstractmethod
    def build(self, app_context: ApplicationContext, requirement: str) -> Dict[str, Any]:
        """Build a targeted context for generation."""
        pass

class ITestNormalizer(ABC):
    @abstractmethod
    def normalize(self, test: CandidateTest) -> CandidateTest:
        """Deterministically normalize test case formatting."""
        pass

class ITestDeduplicator(ABC):
    @abstractmethod
    def deduplicate(self, tests: List[CandidateTest]) -> List[CandidateTest]:
        """Deduplicate and merge similar test cases."""
        pass
