"""
Phase 4 — Bootstrap Ranking Service.

Deterministic fallback prioritization when Transformer is untrained.
Uses documented weights applied to the 9 extracted features.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import numpy as np

from agentqe.models.test_case import CandidateTest
from agentqe.prioritization.feature_extractor import Phase4FeatureExtractor, FeatureVector
from agentqe.enrichment.service import EnrichmentContext

logger = logging.getLogger(__name__)


@dataclass
class RankingWeights:
    """
    Documented bootstrap ranking weights.
    
    These weights are NOT learned. They are heuristic defaults that can be
    adjusted based on domain expertise. All weights sum to 1.0.
    
    Feature order (from Phase4FeatureExtractor.FEATURE_NAMES):
    0. requirement_relevance
    1. risk_relevance
    2. coverage
    3. api_relevance
    4. execution_complexity (inverted: simpler = higher)
    5. evidence_confidence
    6. cross_modal_evidence
    7. test_layer_signal
    8. traceability_completeness
    """
    # Weights for each feature (must sum to 1.0)
    weights: List[float] = field(default_factory=lambda: [
        0.20,  # requirement_relevance - highest weight: tests covering requirements are critical
        0.15,  # risk_relevance - high weight: tests covering risk areas prevent high-severity bugs
        0.10,  # coverage - moderate: broad coverage is good but not everything
        0.10,  # api_relevance - moderate: API tests catch integration issues
        0.10,  # execution_complexity - moderate: prefer simpler tests for faster feedback
        0.10,  # evidence_confidence - moderate: well-evidenced tests are more reliable
        0.05,  # cross_modal_evidence - lower: nice to have but not essential
        0.10,  # test_layer_signal - moderate: security/integration tests prioritized
        0.10,  # traceability_completeness - moderate: traceable tests are maintainable
    ])
    
    def __post_init__(self):
        total = sum(self.weights)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        if len(self.weights) != 9:
            raise ValueError(f"Must have exactly 9 weights, got {len(self.weights)}")
    
    def to_dict(self) -> Dict[str, float]:
        feature_names = [
            "requirement_relevance",
            "risk_relevance",
            "coverage",
            "api_relevance",
            "execution_complexity",
            "evidence_confidence",
            "cross_modal_evidence",
            "test_layer_signal",
            "traceability_completeness",
        ]
        return dict(zip(feature_names, self.weights))


@dataclass
class RankedTest:
    """A test with its ranking information."""
    test: CandidateTest
    feature_vector: FeatureVector
    bootstrap_score: float
    rank: int
    ranking_mode: str = "bootstrap"
    model_status: str = "untrained"
    model_version: str = "phase4-v1"
    explanation: str = ""
    feature_contributions: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test": self.test.to_dict(),
            "feature_vector": self.feature_vector.to_dict(),
            "bootstrap_score": round(self.bootstrap_score, 4),
            "rank": self.rank,
            "ranking_mode": self.ranking_mode,
            "model_status": self.model_status,
            "model_version": self.model_version,
            "explanation": self.explanation,
            "feature_contributions": {k: round(v, 4) for k, v in self.feature_contributions.items()},
        }


class BootstrapRanker:
    """
    Deterministic bootstrap ranker for test prioritization.
    
    Computes scores as weighted sum of 9 features.
    Same inputs ALWAYS produce same scores, ordering, and explanations.
    """
    
    def __init__(self, weights: Optional[RankingWeights] = None):
        self.weights = weights or RankingWeights()
        self.feature_extractor = Phase4FeatureExtractor()
        self._version = "phase4-v1"
    
    def rank(
        self,
        tests: List[CandidateTest],
        context: Optional[EnrichmentContext] = None,
    ) -> List[RankedTest]:
        """
        Rank tests using deterministic bootstrap scoring.
        
        Args:
            tests: List of enriched CandidateTests
            context: Optional enrichment context
            
        Returns:
            List of RankedTest sorted by score descending (highest priority first)
        """
        if not tests:
            return []
        
        # Extract features for all tests
        feature_vectors = self.feature_extractor.extract_batch(tests, context)
        
        # Compute bootstrap scores
        ranked_tests = []
        for test, fv in zip(tests, feature_vectors):
            score = self._compute_score(fv.feature_values)
            contributions = self._compute_contributions(fv.feature_values)
            explanation = self._generate_explanation(fv.feature_values, contributions, test)
            
            ranked_tests.append(RankedTest(
                test=test,
                feature_vector=fv,
                bootstrap_score=score,
                rank=0,  # Will be set after sorting
                ranking_mode="bootstrap",
                model_status="untrained",
                model_version=self._version,
                explanation=explanation,
                feature_contributions=contributions,
            ))
        
        # Sort by score descending
        ranked_tests.sort(key=lambda rt: rt.bootstrap_score, reverse=True)
        
        # Assign ranks
        for i, rt in enumerate(ranked_tests):
            rt.rank = i + 1
        
        return ranked_tests
    
    def _compute_score(self, features: List[float]) -> float:
        """Compute weighted sum of features."""
        return float(np.dot(features, self.weights.weights))
    
    def _compute_contributions(self, features: List[float]) -> Dict[str, float]:
        """Compute per-feature contribution to score."""
        feature_names = [
            "requirement_relevance",
            "risk_relevance",
            "coverage",
            "api_relevance",
            "execution_complexity",
            "evidence_confidence",
            "cross_modal_evidence",
            "test_layer_signal",
            "traceability_completeness",
        ]
        contributions = {}
        for name, feat_val, weight in zip(feature_names, features, self.weights.weights):
            contributions[name] = feat_val * weight
        return contributions
    
    def _generate_explanation(
        self,
        features: List[float],
        contributions: Dict[str, float],
        test: CandidateTest,
    ) -> str:
        """Generate human-readable explanation for the ranking."""
        # Find top contributing features
        sorted_contrib = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        top_features = [name for name, val in sorted_contrib[:3] if val > 0.01]
        
        explanations = []
        
        if "requirement_relevance" in top_features:
            explanations.append("covers high-priority requirements")
        if "risk_relevance" in top_features:
            explanations.append("targets identified risk areas")
        if "coverage" in top_features:
            explanations.append("provides broad application coverage")
        if "api_relevance" in top_features:
            explanations.append("exercises critical API endpoints")
        if "execution_complexity" in top_features:
            explanations.append("is fast to execute")
        if "evidence_confidence" in top_features:
            explanations.append("has strong supporting evidence")
        if "cross_modal_evidence" in top_features:
            explanations.append("has cross-modal evidence")
        if "test_layer_signal" in top_features:
            explanations.append(f"is a {test.test_type} test from {test.perspective} perspective")
        if "traceability_completeness" in top_features:
            explanations.append("has complete traceability")
        
        if not explanations:
            return f"Test {test.test_id} ranked by bootstrap prioritization."
        
        base = f"High priority because the test {', '.join(explanations)}."
        return base


class TransformerRankerWrapper:
    """
    Wrapper for the existing Transformer ranker that handles untrained/trained modes.
    
    If trained weights are available, uses Transformer. Otherwise falls back to bootstrap.
    Never silently uses random weights as meaningful scores.
    """
    
    def __init__(self, bootstrap_ranker: Optional[BootstrapRanker] = None):
        self.bootstrap_ranker = bootstrap_ranker or BootstrapRanker()
        self.feature_extractor = Phase4FeatureExtractor()
        self._transformer_model = None
        self._transformer_loaded = False
        self._model_status = "untrained"
        self._model_version = "phase4-v1"
        # Attempt to load trained model on initialization
        self.load_transformer()
    
    def load_transformer(self, model_path: Optional[str] = None) -> bool:
        """
        Attempt to load trained Transformer weights.
        
        Args:
            model_path: Path to trained model checkpoint
            
        Returns:
            True if trained model loaded successfully, False otherwise
        """
        if model_path is None:
            # Check default location relative to backend
            import os
            # Try multiple possible paths
            possible_paths = [
                os.path.join("backend", "agentqe", "models", "transformer_ranker.pt"),
                os.path.join("agentqe", "models", "transformer_ranker.pt"),
                os.path.join("models", "transformer_ranker.pt"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    model_path = path
                    break
            else:
                logger.info("No trained Transformer weights found in default locations")
                return False
        
        try:
            import torch
            from agentqe.ml.transformer_ranker import TransformerTestRanker
            
            if not os.path.exists(model_path):
                logger.info(f"No trained Transformer weights found at {model_path}")
                return False
            
            # Load model
            model = TransformerTestRanker()
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
            model.eval()
            
            # Validate model architecture
            self._validate_model(model)
            
            # Load metadata if available
            metadata = self._load_metadata(model_path)
            if metadata:
                self._model_version = metadata.get("model_version", "phase4-v1-trained")
                logger.info(f"Loaded model version: {self._model_version}")
            else:
                self._model_version = "phase4-v1-trained"
            
            self._transformer_model = model
            self._transformer_loaded = True
            self._model_status = "trained"
            logger.info(f"Loaded trained Transformer weights from {model_path}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load Transformer weights: {e}")
            self._transformer_model = None
            self._transformer_loaded = False
            self._model_status = "untrained"
            self._model_version = "phase4-v1"
            return False
    
    def _validate_model(self, model) -> None:
        """Validate that model architecture is compatible."""
        # Check input dimension is 9
        if model.input_projection.in_features != 9:
            raise ValueError(
                f"Model input dimension mismatch: expected 9, got {model.input_projection.in_features}"
            )
        
        # Check d_model is 64
        if model.input_projection.out_features != 64:
            raise ValueError(
                f"Model d_model mismatch: expected 64, got {model.input_projection.out_features}"
            )
    
    def _load_metadata(self, model_path: str) -> Optional[Dict[str, Any]]:
        """Load model metadata if available."""
        import os
        import json
        
        metadata_path = model_path.replace(".pt", "_metadata.json")
        
        if not os.path.exists(metadata_path):
            return None
        
        try:
            with open(metadata_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
            return None
    
    def rank(
        self,
        tests: List[CandidateTest],
        context: Optional[EnrichmentContext] = None,
    ) -> List[RankedTest]:
        """
        Rank tests using Transformer if trained, otherwise bootstrap.
        
        Always returns RankedTest objects with explicit ranking_mode and model_status.
        """
        if self._transformer_loaded and self._transformer_model is not None:
            return self._rank_with_transformer(tests, context)
        else:
            return self._rank_with_bootstrap(tests, context)
    
    def _rank_with_bootstrap(
        self,
        tests: List[CandidateTest],
        context: Optional[EnrichmentContext] = None,
    ) -> List[RankedTest]:
        """Rank using bootstrap (deterministic)."""
        ranked = self.bootstrap_ranker.rank(tests, context)
        for rt in ranked:
            rt.ranking_mode = "bootstrap"
            rt.model_status = "untrained"
            rt.model_version = self._model_version
        return ranked
    
    def _rank_with_transformer(
        self,
        tests: List[CandidateTest],
        context: Optional[EnrichmentContext] = None,
    ) -> List[RankedTest]:
        """Rank using trained Transformer."""
        # Extract features using Phase4FeatureExtractor (same as bootstrap)
        feature_vectors = self.feature_extractor.extract_batch(tests, context)
        
        # Convert to tensor for Transformer
        import torch
        import numpy as np
        
        features_array = np.array([fv.feature_values for fv in feature_vectors], dtype=np.float32)
        # Transformer expects batch x seq_len x features, but we have single vector per test
        # Add sequence dimension (seq_len=1)
        x = torch.tensor(features_array).unsqueeze(1)
        
        with torch.no_grad():
            scores = self._transformer_model(x).squeeze(-1).numpy()
        
        ranked_tests = []
        for test, fv, score in zip(tests, feature_vectors, scores):
            contributions = self._compute_transformer_contributions(fv.feature_values, score)
            explanation = self._generate_transformer_explanation(fv.feature_values, test)
            
            ranked_tests.append(RankedTest(
                test=test,
                feature_vector=fv,
                bootstrap_score=float(score),
                rank=0,
                ranking_mode="transformer",
                model_status="trained",
                model_version=self._model_version,
                explanation=explanation,
                feature_contributions=contributions,
            ))
        
        # Sort by score descending
        ranked_tests.sort(key=lambda rt: rt.bootstrap_score, reverse=True)
        
        for i, rt in enumerate(ranked_tests):
            rt.rank = i + 1
        
        return ranked_tests
    
    def _compute_transformer_contributions(self, features: List[float], score: float) -> Dict[str, float]:
        """Approximate feature contributions for Transformer (using bootstrap weights as proxy)."""
        # Since Transformer is a black box, we use bootstrap weights as proxy for explanation
        feature_names = [
            "requirement_relevance",
            "risk_relevance",
            "coverage",
            "api_relevance",
            "execution_complexity",
            "evidence_confidence",
            "cross_modal_evidence",
            "test_layer_signal",
            "traceability_completeness",
        ]
        weights = self.bootstrap_ranker.weights.weights
        return {name: feat * weight for name, feat, weight in zip(feature_names, features, weights)}
    
    def _generate_transformer_explanation(self, features: List[float], test: CandidateTest) -> str:
        """Generate explanation for Transformer ranking (uses bootstrap logic as proxy)."""
        contributions = self._compute_transformer_contributions(features, 0)
        return self.bootstrap_ranker._generate_explanation(features, contributions, test)
    
    @property
    def model_status(self) -> str:
        return self._model_status
    
    @property
    def model_version(self) -> str:
        return self._model_version
    
    @property
    def ranking_mode(self) -> str:
        return "transformer" if self._transformer_loaded else "bootstrap"


__all__ = [
    "BootstrapRanker",
    "RankingWeights",
    "RankedTest",
    "TransformerRankerWrapper",
]