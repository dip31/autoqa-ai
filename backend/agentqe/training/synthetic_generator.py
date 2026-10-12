"""
Synthetic data generator for Phase 4.5 Transformer training.

Generates realistic synthetic test prioritization examples with:
- Domain-constrained scenarios
- Meaningful feature correlations
- Deterministic target generation
- Reproducible with seed
"""

import random
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import numpy as np


@dataclass
class SyntheticExample:
    """A single synthetic training example."""
    id: str
    scenario: str
    test_layer: str
    features: Dict[str, float]
    priority_target: float
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        if self.metadata is None:
            result["metadata"] = {}
        return result


class SyntheticDataGenerator:
    """
    Generates synthetic test prioritization data for bootstrap Transformer training.
    
    The generator creates realistic software testing scenarios with meaningful
    correlations between the 9 Phase 4 features and priority targets.
    """
    
    # Feature names (must match Phase4FeatureExtractor.FEATURE_NAMES)
    FEATURE_NAMES = [
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
    
    # Scenario definitions with feature correlations
    SCENARIOS = [
        # HIGH PRIORITY SCENARIOS
        {
            "name": "high_risk_api_regression",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.85, 0.98),
                "risk_relevance": (0.90, 0.98),
                "coverage": (0.80, 0.95),
                "api_relevance": (0.90, 0.99),
                "execution_complexity": (0.30, 0.60),
                "evidence_confidence": (0.85, 0.95),
                "cross_modal_evidence": (0.60, 0.85),
                "test_layer_signal": (0.80, 0.95),
                "traceability_completeness": (0.85, 0.98),
            },
            "target_boost": 0.15,
        },
        {
            "name": "authentication_security_flow",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.90, 0.99),
                "risk_relevance": (0.95, 0.99),
                "coverage": (0.70, 0.90),
                "api_relevance": (0.85, 0.95),
                "execution_complexity": (0.40, 0.70),
                "evidence_confidence": (0.80, 0.95),
                "cross_modal_evidence": (0.50, 0.75),
                "test_layer_signal": (0.95, 1.0),
                "traceability_completeness": (0.90, 0.99),
            },
            "target_boost": 0.20,
        },
        {
            "name": "high_value_api_integration",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.80, 0.95),
                "risk_relevance": (0.75, 0.90),
                "coverage": (0.85, 0.98),
                "api_relevance": (0.95, 0.99),
                "execution_complexity": (0.35, 0.65),
                "evidence_confidence": (0.80, 0.92),
                "cross_modal_evidence": (0.55, 0.80),
                "test_layer_signal": (0.75, 0.90),
                "traceability_completeness": (0.80, 0.95),
            },
            "target_boost": 0.12,
        },
        {
            "name": "core_user_journey",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.90, 0.98),
                "risk_relevance": (0.80, 0.92),
                "coverage": (0.85, 0.95),
                "api_relevance": (0.60, 0.80),
                "execution_complexity": (0.40, 0.70),
                "evidence_confidence": (0.85, 0.95),
                "cross_modal_evidence": (0.80, 0.95),
                "test_layer_signal": (0.60, 0.75),
                "traceability_completeness": (0.85, 0.98),
            },
            "target_boost": 0.18,
        },
        {
            "name": "high_requirement_coverage",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.92, 0.99),
                "risk_relevance": (0.70, 0.85),
                "coverage": (0.90, 0.98),
                "api_relevance": (0.50, 0.70),
                "execution_complexity": (0.45, 0.75),
                "evidence_confidence": (0.80, 0.92),
                "cross_modal_evidence": (0.70, 0.90),
                "test_layer_signal": (0.55, 0.70),
                "traceability_completeness": (0.90, 0.99),
            },
            "target_boost": 0.10,
        },
        
        # MEDIUM PRIORITY SCENARIOS
        {
            "name": "high_evidence_confidence",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.60, 0.80),
                "risk_relevance": (0.50, 0.70),
                "coverage": (0.60, 0.80),
                "api_relevance": (0.40, 0.60),
                "execution_complexity": (0.50, 0.80),
                "evidence_confidence": (0.90, 0.98),
                "cross_modal_evidence": (0.75, 0.92),
                "test_layer_signal": (0.50, 0.65),
                "traceability_completeness": (0.70, 0.85),
            },
            "target_boost": 0.05,
        },
        {
            "name": "cross_modal_ui_test",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.55, 0.75),
                "risk_relevance": (0.45, 0.65),
                "coverage": (0.55, 0.75),
                "api_relevance": (0.30, 0.50),
                "execution_complexity": (0.55, 0.85),
                "evidence_confidence": (0.75, 0.90),
                "cross_modal_evidence": (0.85, 0.98),
                "test_layer_signal": (0.50, 0.65),
                "traceability_completeness": (0.65, 0.80),
            },
            "target_boost": 0.03,
        },
        {
            "name": "high_coverage_regression",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.70, 0.85),
                "risk_relevance": (0.65, 0.80),
                "coverage": (0.88, 0.98),
                "api_relevance": (0.70, 0.85),
                "execution_complexity": (0.35, 0.65),
                "evidence_confidence": (0.70, 0.85),
                "cross_modal_evidence": (0.50, 0.70),
                "test_layer_signal": (0.70, 0.85),
                "traceability_completeness": (0.75, 0.88),
            },
            "target_boost": 0.08,
        },
        {
            "name": "business_critical_workflow",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.85, 0.95),
                "risk_relevance": (0.75, 0.88),
                "coverage": (0.75, 0.90),
                "api_relevance": (0.55, 0.75),
                "execution_complexity": (0.45, 0.75),
                "evidence_confidence": (0.75, 0.88),
                "cross_modal_evidence": (0.65, 0.82),
                "test_layer_signal": (0.60, 0.75),
                "traceability_completeness": (0.80, 0.92),
            },
            "target_boost": 0.14,
        },
        {
            "name": "edge_case_test",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.50, 0.70),
                "risk_relevance": (0.60, 0.78),
                "coverage": (0.40, 0.60),
                "api_relevance": (0.65, 0.82),
                "execution_complexity": (0.50, 0.80),
                "evidence_confidence": (0.55, 0.72),
                "cross_modal_evidence": (0.35, 0.55),
                "test_layer_signal": (0.65, 0.80),
                "traceability_completeness": (0.50, 0.68),
            },
            "target_boost": 0.02,
        },
        
        # LOW PRIORITY SCENARIOS
        {
            "name": "low_risk_smoke_test",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.30, 0.50),
                "risk_relevance": (0.20, 0.40),
                "coverage": (0.30, 0.50),
                "api_relevance": (0.20, 0.40),
                "execution_complexity": (0.70, 0.90),
                "evidence_confidence": (0.40, 0.60),
                "cross_modal_evidence": (0.30, 0.50),
                "test_layer_signal": (0.30, 0.45),
                "traceability_completeness": (0.35, 0.55),
            },
            "target_boost": -0.10,
        },
        {
            "name": "low_value_duplicate",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.25, 0.45),
                "risk_relevance": (0.15, 0.35),
                "coverage": (0.20, 0.40),
                "api_relevance": (0.15, 0.35),
                "execution_complexity": (0.60, 0.85),
                "evidence_confidence": (0.30, 0.50),
                "cross_modal_evidence": (0.25, 0.45),
                "test_layer_signal": (0.25, 0.40),
                "traceability_completeness": (0.30, 0.50),
            },
            "target_boost": -0.15,
        },
        {
            "name": "expensive_complex_test",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.40, 0.60),
                "risk_relevance": (0.35, 0.55),
                "coverage": (0.50, 0.70),
                "api_relevance": (0.40, 0.60),
                "execution_complexity": (0.05, 0.20),  # Very complex (low score)
                "evidence_confidence": (0.45, 0.65),
                "cross_modal_evidence": (0.40, 0.60),
                "test_layer_signal": (0.35, 0.50),
                "traceability_completeness": (0.45, 0.65),
            },
            "target_boost": -0.12,
        },
        {
            "name": "weakly_traceable_test",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.45, 0.65),
                "risk_relevance": (0.40, 0.60),
                "coverage": (0.45, 0.65),
                "api_relevance": (0.50, 0.70),
                "execution_complexity": (0.50, 0.75),
                "evidence_confidence": (0.40, 0.60),
                "cross_modal_evidence": (0.30, 0.50),
                "test_layer_signal": (0.55, 0.70),
                "traceability_completeness": (0.15, 0.35),
            },
            "target_boost": -0.08,
        },
        {
            "name": "low_evidence_exploratory",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.35, 0.55),
                "risk_relevance": (0.30, 0.50),
                "coverage": (0.35, 0.55),
                "api_relevance": (0.25, 0.45),
                "execution_complexity": (0.55, 0.80),
                "evidence_confidence": (0.20, 0.40),
                "cross_modal_evidence": (0.20, 0.40),
                "test_layer_signal": (0.35, 0.50),
                "traceability_completeness": (0.30, 0.50),
            },
            "target_boost": -0.12,
        },
        {
            "name": "negative_error_handling",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.55, 0.75),
                "risk_relevance": (0.65, 0.82),
                "coverage": (0.40, 0.60),
                "api_relevance": (0.60, 0.78),
                "execution_complexity": (0.45, 0.70),
                "evidence_confidence": (0.50, 0.68),
                "cross_modal_evidence": (0.35, 0.55),
                "test_layer_signal": (0.60, 0.75),
                "traceability_completeness": (0.55, 0.72),
            },
            "target_boost": 0.04,
        },
        {
            "name": "performance_sensitive",
            "test_layer": "api",
            "feature_ranges": {
                "requirement_relevance": (0.60, 0.78),
                "risk_relevance": (0.55, 0.72),
                "coverage": (0.45, 0.65),
                "api_relevance": (0.65, 0.82),
                "execution_complexity": (0.25, 0.50),
                "evidence_confidence": (0.55, 0.72),
                "cross_modal_evidence": (0.40, 0.60),
                "test_layer_signal": (0.80, 0.95),
                "traceability_completeness": (0.60, 0.78),
            },
            "target_boost": 0.06,
        },
        {
            "name": "low_priority_cosmetic",
            "test_layer": "ui",
            "feature_ranges": {
                "requirement_relevance": (0.20, 0.40),
                "risk_relevance": (0.15, 0.30),
                "coverage": (0.25, 0.45),
                "api_relevance": (0.10, 0.30),
                "execution_complexity": (0.60, 0.85),
                "evidence_confidence": (0.35, 0.55),
                "cross_modal_evidence": (0.50, 0.70),
                "test_layer_signal": (0.20, 0.35),
                "traceability_completeness": (0.25, 0.45),
            },
            "target_boost": -0.18,
        },
    ]
    
    # Bootstrap weights for base calculation (from bootstrap_ranker.py)
    BOOTSTRAP_WEIGHTS = np.array([
        0.20,  # requirement_relevance
        0.15,  # risk_relevance
        0.10,  # coverage
        0.10,  # api_relevance
        0.10,  # execution_complexity
        0.10,  # evidence_confidence
        0.05,  # cross_modal_evidence
        0.10,  # test_layer_signal
        0.10,  # traceability_completeness
    ])
    
    def __init__(self, seed: int = 42):
        """
        Initialize generator with deterministic seed.
        
        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)
    
    def generate(
        self,
        num_examples: int,
        scenario_distribution: Optional[List[float]] = None,
    ) -> List[SyntheticExample]:
        """
        Generate synthetic training examples.
        
        Args:
            num_examples: Number of examples to generate
            scenario_distribution: Optional distribution over scenarios (must sum to 1.0)
                                  If None, uses uniform distribution
        
        Returns:
            List of SyntheticExample objects
        """
        if scenario_distribution is None:
            # Uniform distribution over scenarios
            scenario_distribution = [1.0 / len(self.SCENARIOS)] * len(self.SCENARIOS)
        
        if abs(sum(scenario_distribution) - 1.0) > 0.001:
            raise ValueError("Scenario distribution must sum to 1.0")
        
        examples = []
        for i in range(num_examples):
            # Select scenario based on distribution
            scenario_idx = self._weighted_choice(scenario_distribution)
            scenario = self.SCENARIOS[scenario_idx]
            
            # Generate example
            example = self._generate_example(i, scenario)
            examples.append(example)
        
        return examples
    
    def _weighted_choice(self, weights: List[float]) -> int:
        """Choose index based on weighted distribution."""
        return self.rng.choices(range(len(weights)), weights=weights, k=1)[0]
    
    def _generate_example(self, index: int, scenario: Dict[str, Any]) -> SyntheticExample:
        """Generate a single synthetic example from a scenario."""
        # Generate feature values within scenario ranges
        features = {}
        for feature_name, (min_val, max_val) in scenario["feature_ranges"].items():
            # Uniform random within range
            value = self.rng.uniform(min_val, max_val)
            features[feature_name] = round(value, 4)
        
        # Generate priority target using deterministic formula
        target = self._compute_priority_target(features, scenario["target_boost"])
        target = round(max(0.0, min(1.0, target)), 4)
        
        return SyntheticExample(
            id=f"synthetic_{index:06d}",
            scenario=scenario["name"],
            test_layer=scenario["test_layer"],
            features=features,
            priority_target=target,
            metadata={
                "scenario_boost": scenario["target_boost"],
                "feature_ranges": scenario["feature_ranges"],
            },
        )
    
    def _compute_priority_target(
        self,
        features: Dict[str, float],
        scenario_boost: float,
    ) -> float:
        """
        Compute priority target using deterministic synthetic scoring function.
        
        The target combines:
        1. Base weighted contribution (similar to bootstrap but with different weights)
        2. Nonlinear interaction terms
        3. Scenario-specific boost
        4. Small bounded noise
        
        Formula:
        target = base + interactions + scenario_boost + noise
        
        Where:
        - base: weighted sum with adjusted weights (not identical to bootstrap)
        - interactions: nonlinear feature interactions (e.g., risk * requirement, evidence * traceability)
        - scenario_boost: scenario-specific adjustment
        - noise: small random noise bounded to [-0.02, 0.02]
        """
        # Extract feature values in correct order
        feature_values = np.array([features[name] for name in self.FEATURE_NAMES])
        
        # Base weighted contribution (slightly different from bootstrap to avoid duplication)
        base_weights = np.array([
            0.22,  # requirement_relevance (slightly higher)
            0.16,  # risk_relevance (slightly higher)
            0.09,  # coverage (slightly lower)
            0.11,  # api_relevance (slightly higher)
            0.09,  # execution_complexity (slightly lower)
            0.11,  # evidence_confidence (slightly higher)
            0.04,  # cross_modal_evidence (slightly lower)
            0.09,  # test_layer_signal (slightly lower)
            0.09,  # traceability_completeness (same)
        ])
        base = np.dot(feature_values, base_weights)
        
        # Nonlinear interaction terms
        # High risk + high requirement relevance interaction
        risk_req_interaction = (features["risk_relevance"] * features["requirement_relevance"]) * 0.15
        
        # Strong evidence + high traceability interaction
        evidence_trace_interaction = (features["evidence_confidence"] * features["traceability_completeness"]) * 0.10
        
        # Coverage diminishing returns (log-like)
        coverage_bonus = np.log1p(features["coverage"]) * 0.08
        
        # API relevance matters more for API tests
        api_layer_boost = 0.0
        if features["api_relevance"] > 0.7 and features["test_layer_signal"] > 0.7:
            api_layer_boost = 0.05
        
        # Cross-modal evidence matters more for UI tests
        ui_modal_boost = 0.0
        if features["cross_modal_evidence"] > 0.7 and features["test_layer_signal"] < 0.7:
            ui_modal_boost = 0.04
        
        # Extremely high execution complexity penalty
        complexity_penalty = 0.0
        if features["execution_complexity"] < 0.2:
            complexity_penalty = -0.08
        
        # Combine all terms
        interactions = (
            risk_req_interaction +
            evidence_trace_interaction +
            coverage_bonus +
            api_layer_boost +
            ui_modal_boost +
            complexity_penalty
        )
        
        # Small bounded noise
        noise = self.np_rng.uniform(-0.02, 0.02)
        
        # Final target
        target = base + interactions + scenario_boost + noise
        
        return target
    
    def save_dataset(
        self,
        examples: List[SyntheticExample],
        output_path: str,
    ) -> None:
        """
        Save dataset to JSONL file.
        
        Args:
            examples: List of SyntheticExample objects
            output_path: Path to output file
        """
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, "w") as f:
            for example in examples:
                f.write(json.dumps(example.to_dict()) + "\n")
    
    def load_dataset(self, input_path: str) -> List[SyntheticExample]:
        """
        Load dataset from JSONL file.
        
        Args:
            input_path: Path to input file
        
        Returns:
            List of SyntheticExample objects
        """
        examples = []
        with open(input_path, "r") as f:
            for line in f:
                data = json.loads(line.strip())
                examples.append(SyntheticExample(**data))
        return examples


__all__ = ["SyntheticDataGenerator", "SyntheticExample"]
