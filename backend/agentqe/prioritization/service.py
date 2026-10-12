"""
Phase 4 — Test Prioritization Service.

Orchestrates the full prioritization pipeline:
CandidateTest[] → Enrichment → Feature Extraction → Ranking → Ranked CandidateTests
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from agentqe.models.test_case import CandidateTest
from agentqe.models.context import ApplicationContext
from agentqe.enrichment.service import TestEnricher, EnrichmentContext, EnrichmentResult
from agentqe.prioritization.feature_extractor import Phase4FeatureExtractor, FeatureVector
from agentqe.prioritization.bootstrap_ranker import (
    BootstrapRanker,
    RankedTest,
    TransformerRankerWrapper,
    RankingWeights,
)

logger = logging.getLogger(__name__)


@dataclass
class PrioritizationResult:
    """Result of the prioritization pipeline."""
    ranked_tests: List[RankedTest]
    enrichment_results: List[EnrichmentResult]
    feature_vectors: List[FeatureVector]
    ranking_mode: str
    model_status: str
    model_version: str
    feature_version: str
    total_tests: int
    enriched_tests: int
    failed_enrichments: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ranked_tests": [rt.to_dict() for rt in self.ranked_tests],
            "enrichment_summary": {
                "total": self.total_tests,
                "enriched": self.enriched_tests,
                "failed": self.failed_enrichments,
            },
            "ranking_metadata": {
                "ranking_mode": self.ranking_mode,
                "model_status": self.model_status,
                "model_version": self.model_version,
                "feature_version": self.feature_version,
            },
        }


class TestPrioritizationService:
    """
    Phase 4 Test Prioritization Service.
    
    Pipeline:
    1. Enrich CandidateTests with application knowledge
    2. Extract 9 deterministic features
    3. Rank using Transformer (if trained) or Bootstrap (deterministic)
    4. Return ranked tests with explanations and metadata
    """
    
    def __init__(
        self,
        enricher: Optional[TestEnricher] = None,
        ranker: Optional[TransformerRankerWrapper] = None,
        bootstrap_ranker: Optional[BootstrapRanker] = None,
    ):
        self.enricher = enricher or TestEnricher()
        self.feature_extractor = Phase4FeatureExtractor()
        
        # Initialize rankers
        self.bootstrap_ranker = bootstrap_ranker or BootstrapRanker()
        self.ranker = ranker or TransformerRankerWrapper(self.bootstrap_ranker)
        
        logger.info(f"TestPrioritizationService initialized with ranking_mode={self.ranker.ranking_mode}")
    
    def prioritize(
        self,
        tests: List[CandidateTest],
        app_context: Optional[ApplicationContext] = None,
        knowledge_model: Optional[Any] = None,  # ApplicationKnowledgeModel
        unified_model: Optional[Dict[str, Any]] = None,
        rag_context: Optional[Dict[str, Any]] = None,
        execution_history: Optional[Dict[str, Dict[str, float]]] = None,
        repository_data: Optional[Dict[str, Any]] = None,
    ) -> PrioritizationResult:
        """
        Run the full prioritization pipeline.
        
        Args:
            tests: List of CandidateTests to prioritize
            app_context: ApplicationContext from Phase 1/1.5
            knowledge_model: ApplicationKnowledgeModel from Phase 1.5
            unified_model: UnifiedApplicationModel from Phase 1.5
            rag_context: RAG retrieval context
            execution_history: Historical execution data
            repository_data: Repository analysis data
            
        Returns:
            PrioritizationResult with ranked tests and metadata
        """
        if not tests:
            return PrioritizationResult(
                ranked_tests=[],
                enrichment_results=[],
                feature_vectors=[],
                ranking_mode=self.ranker.ranking_mode,
                model_status=self.ranker.model_status,
                model_version=self.ranker.model_version,
                feature_version="phase4-v1",
                total_tests=0,
                enriched_tests=0,
                failed_enrichments=0,
            )
        
        # Step 1: Build enrichment context
        enrichment_context = EnrichmentContext(
            app_context=app_context,
            knowledge_model=knowledge_model,
            unified_model=unified_model,
            rag_context=rag_context,
            execution_history=execution_history or {},
            repository_data=repository_data or {},
        )
        
        # Step 2: Enrich tests
        logger.info(f"Enriching {len(tests)} tests...")
        enriched_tests = self.enricher.enrich(tests, enrichment_context)
        
        enrichment_results = []
        enriched_count = 0
        failed_count = 0
        for test in enriched_tests:
            if test.metadata.get("enriched", False):
                enriched_count += 1
                enrichment_results.append(EnrichmentResult(
                    test_id=test.test_id,
                    enriched=True,
                    added_fields=test.metadata.get("enriched_fields", []),
                ))
            else:
                failed_count += 1
                enrichment_results.append(EnrichmentResult(
                    test_id=test.test_id,
                    enriched=False,
                    error=test.metadata.get("enrichment_error", "Unknown"),
                    error_code=test.metadata.get("enrichment_error_code", "ENRICHMENT_ERROR"),
                ))
        
        logger.info(f"Enrichment complete: {enriched_count} enriched, {failed_count} failed")
        
        # Step 3: Extract features
        logger.info("Extracting features...")
        feature_vectors = self.feature_extractor.extract_batch(enriched_tests, enrichment_context)
        
        # Step 4: Rank tests
        logger.info(f"Ranking tests using {self.ranker.ranking_mode} mode...")
        ranked_tests = self.ranker.rank(enriched_tests, enrichment_context)
        
        logger.info(f"Prioritization complete: {len(ranked_tests)} tests ranked")
        
        return PrioritizationResult(
            ranked_tests=ranked_tests,
            enrichment_results=enrichment_results,
            feature_vectors=feature_vectors,
            ranking_mode=self.ranker.ranking_mode,
            model_status=self.ranker.model_status,
            model_version=self.ranker.model_version,
            feature_version="phase4-v1",
            total_tests=len(tests),
            enriched_tests=enriched_count,
            failed_enrichments=failed_count,
        )
    
    def get_ranking_metadata(self) -> Dict[str, Any]:
        """Get current ranking configuration metadata."""
        return {
            "ranking_mode": self.ranker.ranking_mode,
            "model_status": self.ranker.model_status,
            "model_version": self.ranker.model_version,
            "feature_version": "phase4-v1",
            "bootstrap_weights": self.bootstrap_ranker.weights.to_dict(),
            "feature_names": Phase4FeatureExtractor.FEATURE_NAMES,
        }


__all__ = [
    "TestPrioritizationService",
    "PrioritizationResult",
]