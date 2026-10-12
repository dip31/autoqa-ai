import logging
import time
from typing import Dict, Any, List, Optional

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from .models import GroqTestGenerationModel, GenerationError
from .user_test_generator import UserTestGenerator
from .engineering_test_generator import EngineeringTestGenerator
from .context_limiter import BoundedContextBuilder
from .normalizer import DeterministicTestNormalizer
from .deduplicator import DeterministicDeduplicator

# Optional RAG import
try:
    from agentqe.rag.service import RAGService
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    RAGService = None

logger = logging.getLogger(__name__)

class GeneratorResult:
    """Structured result from a single generator."""
    def __init__(self, agent_name: str, candidates: List[CandidateTest] = None, error: str = None, error_code: str = None):
        self.agent_name = agent_name
        self.candidates = candidates or []
        self.error = error
        self.error_code = error_code
    
    @property
    def success(self) -> bool:
        return self.error is None
    
    @property
    def count(self) -> int:
        return len(self.candidates)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "agent": self.agent_name,
            "status": "success" if self.success else "failed",
            "candidate_count": self.count,
        }
        if not self.success:
            result["error"] = self.error
            result["error_code"] = self.error_code
        return result


class TestGenerationService:
    def __init__(self, rag_service: Optional[RAGService] = None):
        if not rag_service and RAG_AVAILABLE:
            rag_service = RAGService()
        self.rag_service = rag_service
        self.context_builder = BoundedContextBuilder(self.rag_service)
        
        llm = GroqTestGenerationModel()
        self.user_agent = UserTestGenerator(llm)
        self.engineering_agent = EngineeringTestGenerator(llm)
        
        self.normalizer = DeterministicTestNormalizer()
        self.deduplicator = DeterministicDeduplicator()

    def generate_tests(self, app_context: ApplicationContext, requirement: str, max_tests: int = 10) -> Dict[str, Any]:
        """Generate candidates for a given requirement."""
        start_time = time.time()
        
        generator_results = []
        candidate_pool: List[CandidateTest] = []

        # 2. Run User Test Agent
        logger.info("Running User Test Generator...")
        user_ctx = self.context_builder.build(app_context, requirement, agent_type="user")
        user_result = self._run_generator("user_agent", self.user_agent, user_ctx)
        generator_results.append(user_result)
        candidate_pool.extend(user_result.candidates)

        # 3. Run Engineering Test Agent
        logger.info("Running Engineering Test Generator...")
        eng_ctx = self.context_builder.build(app_context, requirement, agent_type="engineering")
        eng_result = self._run_generator("engineering_agent", self.engineering_agent, eng_ctx)
        generator_results.append(eng_result)
        candidate_pool.extend(eng_result.candidates)

        # Determine overall status
        successful_generators = [r for r in generator_results if r.success]
        failed_generators = [r for r in generator_results if not r.success]
        
        if not candidate_pool:
            # Both generators failed
            overall_status = "failed"
        elif failed_generators:
            # Partial failure
            overall_status = "partial_failure"
        else:
            # All succeeded
            overall_status = "success"

        # 4. Normalize
        normalized_pool = [self.normalizer.normalize(t) for t in candidate_pool]
        
        # 5. Deduplicate
        final_tests = self.deduplicator.deduplicate(normalized_pool)
        
        # Determine how many were merged
        merged_count = len(normalized_pool) - len(final_tests)
        
        # Limit by max_tests if needed
        final_tests = final_tests[:max_tests]

        duration_ms = round((time.time() - start_time) * 1000, 2)
        
        summary = {
            "total_candidates": len(normalized_pool),
            "user_agent": user_result.count,
            "engineering_agent": eng_result.count,
            "merged": merged_count,
            "final_tests": len(final_tests),
            "duration_ms": duration_ms
        }

        return {
            "status": overall_status,
            "generation_summary": summary,
            "candidate_tests": [t.to_dict() for t in final_tests],
            "generators": [r.to_dict() for r in generator_results],
        }

    def _run_generator(self, agent_name: str, generator, gen_ctx: Dict[str, Any]) -> GeneratorResult:
        """Run a single generator and return structured result."""
        try:
            candidates = generator.generate(gen_ctx)
            return GeneratorResult(agent_name, candidates=candidates)
        except GenerationError as e:
            # Structured generation error
            logger.error(f"{agent_name} failed with error_code={e.error_code}: {e.message}")
            return GeneratorResult(agent_name, error=e.message, error_code=e.error_code)
        except Exception as e:
            error_str = str(e)
            error_code = "UNKNOWN_ERROR"
            if "model_decommissioned" in error_str or "decommissioned" in error_str:
                error_code = "MODEL_DECOMMISSIONED"
            elif "400" in error_str:
                error_code = "BAD_REQUEST"
            elif "401" in error_str or "unauthorized" in error_str.lower():
                error_code = "UNAUTHORIZED"
            elif "429" in error_str or "rate" in error_str.lower():
                error_code = "RATE_LIMITED"
            elif "timeout" in error_str.lower():
                error_code = "TIMEOUT"
            logger.error(f"{agent_name} failed: {error_str}")
            return GeneratorResult(agent_name, error=error_str, error_code=error_code)
