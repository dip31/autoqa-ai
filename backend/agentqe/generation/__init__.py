"""
Phase 3 — Intelligent Test Generation Layer
"""
from .service import TestGenerationService
from .interfaces import ITestGenerationModel, ITestGenerator, IContextBuilder, ITestNormalizer, ITestDeduplicator
from .schemas import GenerationContext
from .models import GroqTestGenerationModel, GenerationError
from .context_limiter import BoundedContextBuilder
from .user_test_generator import UserTestGenerator
from .engineering_test_generator import EngineeringTestGenerator
from .normalizer import DeterministicTestNormalizer
from .deduplicator import DeterministicDeduplicator

# Optional old context builder import
try:
    from .context_builder import DeterministicContextBuilder
    _OLD_BUILDER_AVAILABLE = True
except ImportError:
    _OLD_BUILDER_AVAILABLE = False
    DeterministicContextBuilder = None

__all__ = [
    "TestGenerationService",
    "ITestGenerationModel",
    "ITestGenerator",
    "IContextBuilder",
    "ITestNormalizer",
    "ITestDeduplicator",
    "GenerationContext",
    "GroqTestGenerationModel",
    "GenerationError",
    "BoundedContextBuilder",
    "UserTestGenerator",
    "EngineeringTestGenerator",
    "DeterministicTestNormalizer",
    "DeterministicDeduplicator"
]

if _OLD_BUILDER_AVAILABLE:
    __all__.append("DeterministicContextBuilder")
