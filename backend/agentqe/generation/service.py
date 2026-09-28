import logging
import time
from typing import Dict, Any, List

from agentqe.models.context import ApplicationContext
from agentqe.models.test_case import CandidateTest

from .models import GroqTestGenerationModel
from .user_test_generator import UserTestGenerator
from .engineering_test_generator import EngineeringTestGenerator
from .context_builder import DeterministicContextBuilder
from .normalizer import DeterministicTestNormalizer
from .deduplicator import DeterministicDeduplicator
from agentqe.rag.service import RAGService

logger = logging.getLogger(__name__)

class TestGenerationService:
    def __init__(self, rag_service: RAGService = None):
        if not rag_service:
            rag_service = RAGService()
        self.rag_service = rag_service
        self.context_builder = DeterministicContextBuilder(self.rag_service)
        
        llm = GroqTestGenerationModel()
        self.user_agent = UserTestGenerator(llm)
        self.engineering_agent = EngineeringTestGenerator(llm)
        
        self.normalizer = DeterministicTestNormalizer()
        self.deduplicator = DeterministicDeduplicator()

    def generate_tests(self, app_context: ApplicationContext, requirement: str, max_tests: int = 10) -> Dict[str, Any]:
        """Generate candidates for a given requirement."""
        start_time = time.time()
        
        # 1. Build generation context
        logger.info("Building context for generation...")
        gen_ctx = self.context_builder.build(app_context, requirement)
        
        candidate_pool: List[CandidateTest] = []
        user_tests_count = 0
        engineering_tests_count = 0
        errors = []

        # 2. Run User Test Agent
        logger.info("Running User Test Generator...")
        try:
            user_candidates = self.user_agent.generate(gen_ctx)
            user_tests_count = len(user_candidates)
            candidate_pool.extend(user_candidates)
        except Exception as e:
            logger.error(f"User Test Generator failed: {e}")
            errors.append({"agent": "user_agent", "error": str(e)})

        # 3. Run Engineering Test Agent
        logger.info("Running Engineering Test Generator...")
        try:
            eng_candidates = self.engineering_agent.generate(gen_ctx)
            engineering_tests_count = len(eng_candidates)
            candidate_pool.extend(eng_candidates)
        except Exception as e:
            logger.error(f"Engineering Test Generator failed: {e}")
            errors.append({"agent": "engineering_agent", "error": str(e)})

        if not candidate_pool and errors:
            return {
                "generation_summary": {
                    "total_candidates": 0,
                    "final_tests": 0,
                    "user_agent": 0,
                    "engineering_agent": 0,
                    "merged": 0,
                },
                "candidate_tests": [],
                "errors": errors
            }

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
            "user_agent": user_tests_count,
            "engineering_agent": engineering_tests_count,
            "merged": merged_count,
            "final_tests": len(final_tests),
            "duration_ms": duration_ms
        }

        return {
            "generation_summary": summary,
            "candidate_tests": [t.to_dict() for t in final_tests],
            "errors": errors
        }
