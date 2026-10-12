"""
Phase 4 — Deterministic Feature Extraction for Test Prioritization.

Extracts exactly 9 features from enriched CandidateTest objects.
All features are deterministic, normalized to [0, 1], and have documented calculations.
"""

import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from agentqe.models.test_case import CandidateTest
from agentqe.enrichment.service import EnrichmentContext


@dataclass
class FeatureVector:
    """Container for extracted feature vector with metadata."""
    feature_names: List[str]
    feature_values: List[float]
    feature_version: str = "phase4-v1"
    
    def to_array(self) -> np.ndarray:
        return np.array(self.feature_values, dtype=np.float32)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "feature_values": self.feature_values,
            "feature_version": self.feature_version,
        }


class Phase4FeatureExtractor:
    """
    Deterministic feature extractor for Phase 4 test prioritization.
    
    Extracts exactly 9 features:
    1. requirement_relevance - How well test covers requirements (0-1)
    2. risk_relevance - How well test covers identified risk areas (0-1)
    3. coverage - Page/control/form/API coverage breadth (0-1)
    4. api_relevance - API endpoint coverage (0-1)
    5. execution_complexity - Normalized estimated execution complexity (0-1, lower is simpler)
    6. evidence_confidence - Average confidence of supporting evidence (0-1)
    7. cross_modal_evidence - Fraction of evidence types present (0-1)
    8. test_layer_signal - Test layer/type priority signal (0-1)
    9. traceability_completeness - Fraction of references resolvable (0-1)
    
    All features are deterministic and use observed/inferred/unknown semantics.
    """
    
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
    
    FEATURE_VERSION = "phase4-v1"
    
    def __init__(self):
        # Weights for cross-modal evidence types
        self._evidence_type_weights = {
            "dom": 1.0,
            "accessibility": 1.0,
            "visual": 1.0,
            "network": 1.0,
            "screenshot": 0.5,
        }
    
    def extract(self, test: CandidateTest, context: Optional[EnrichmentContext] = None) -> FeatureVector:
        """
        Extract 9-dimensional feature vector for a single test.
        
        Args:
            test: Enriched CandidateTest
            context: Optional enrichment context for additional data
            
        Returns:
            FeatureVector with 9 normalized features
        """
        features = [
            self._requirement_relevance(test, context),
            self._risk_relevance(test, context),
            self._coverage(test, context),
            self._api_relevance(test, context),
            self._execution_complexity(test, context),
            self._evidence_confidence(test, context),
            self._cross_modal_evidence(test, context),
            self._test_layer_signal(test, context),
            self._traceability_completeness(test, context),
        ]
        
        # Ensure all features are in [0, 1]
        features = [max(0.0, min(1.0, f)) for f in features]
        
        return FeatureVector(
            feature_names=self.FEATURE_NAMES.copy(),
            feature_values=features,
            feature_version=self.FEATURE_VERSION,
        )
    
    def extract_batch(self, tests: List[CandidateTest], context: Optional[EnrichmentContext] = None) -> List[FeatureVector]:
        """Extract features for multiple tests."""
        return [self.extract(test, context) for test in tests]
    
    # --- Individual Feature Calculations ---
    
    def _requirement_relevance(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 1: Requirement Relevance
        
        Calculated as the fraction of test's requirement_refs that are:
        - Present in the knowledge model (observed)
        - Weighted by requirement priority if available
        
        If no requirement_refs, returns 0.0 (unknown).
        """
        req_refs = test.requirement_refs or []
        if not req_refs:
            return 0.0  # unknown
        
        if not context or not context.knowledge_model:
            return 0.5  # inferred (have refs but can't verify)
        
        resolved = 0
        total_weight = 0
        for req_id in req_refs:
            entity = None
            if context.knowledge_model.entities:
                entity = next((e for e in context.knowledge_model.entities if e.id == req_id), None)
            
            if entity:
                resolved += 1
                # Weight by priority if available
                priority = entity.properties.get("priority", "Medium")
                weight = {"High": 1.0, "Medium": 0.5, "Low": 0.2}.get(priority, 0.5)
                total_weight += weight
            else:
                total_weight += 0.5  # unknown priority
        
        if total_weight == 0:
            return 0.0
        
        # Normalize by max possible weight (all High)
        max_weight = len(req_refs) * 1.0
        return min(1.0, total_weight / max_weight)
    
    def _risk_relevance(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 2: Risk Relevance
        
        Calculated as the fraction of matched risk areas (from enrichment) 
        weighted by severity.
        
        If no matched_risk_areas in metadata, returns 0.0.
        """
        matched_risks = test.metadata.get("matched_risk_areas", [])
        if not matched_risks:
            return 0.0
        
        severity_weights = {"Critical": 1.0, "High": 0.8, "Medium": 0.5, "Low": 0.2}
        total_weight = sum(severity_weights.get(r.get("severity", "Medium"), 0.5) for r in matched_risks)
        max_weight = len(matched_risks) * 1.0
        
        return min(1.0, total_weight / max_weight) if max_weight > 0 else 0.0
    
    def _coverage(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 3: Coverage (Page/Control/Form/API breadth)
        
        Calculated as the normalized count of unique entity types referenced.
        Each reference type (page, control, form, api, flow) contributes up to 0.2.
        """
        coverage_score = 0.0
        
        # Pages
        if test.page_refs:
            coverage_score += min(0.2, len(test.page_refs) * 0.05)
        
        # Controls
        if test.control_refs:
            coverage_score += min(0.2, len(test.control_refs) * 0.03)
        
        # Forms
        if test.form_refs:
            coverage_score += min(0.2, len(test.form_refs) * 0.1)
        
        # APIs
        if test.api_refs:
            coverage_score += min(0.2, len(test.api_refs) * 0.1)
        
        # Flows
        if test.flow_refs:
            coverage_score += min(0.2, len(test.flow_refs) * 0.1)
        
        return min(1.0, coverage_score)
    
    def _api_relevance(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 4: API Relevance
        
        Calculated as the fraction of test's api_refs that are:
        - Present in knowledge model (observed)
        - Have observed failures (higher relevance)
        - Are authenticated endpoints
        """
        api_refs = test.api_refs or []
        if not api_refs:
            return 0.0
        
        if not context or not context.knowledge_model:
            return 0.5  # inferred
        
        relevance_score = 0.0
        for api_id in api_refs:
            entity = None
            if context.knowledge_model.entities:
                entity = next((e for e in context.knowledge_model.entities if e.id == api_id), None)
            
            if entity:
                base = 0.5
                # Boost for observed failures
                if entity.properties.get("failure_count", 0) > 0:
                    base += 0.3
                # Boost for authenticated endpoints
                if entity.properties.get("requires_auth", False):
                    base += 0.2
                relevance_score += min(1.0, base)
            else:
                relevance_score += 0.3  # unknown but referenced
        
        return min(1.0, relevance_score / len(api_refs))
    
    def _execution_complexity(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 5: Execution Complexity (normalized, lower is simpler)
        
        Uses enriched estimated_complexity (from enrichment) and normalizes to [0,1].
        Complexity tiers: low(<5) -> 0.2, medium(5-15) -> 0.5, high(>15) -> 0.8
        """
        complexity = test.metadata.get("estimated_complexity")
        if complexity is None:
            # Fallback: estimate from steps and test_type
            base = len(test.steps) * 1.0
            type_mult = {"UNIT": 1.0, "API": 1.5, "UI": 2.5, "INTEGRATION": 3.0, "SECURITY": 3.5, "PERFORMANCE": 4.0}.get(test.test_type, 2.0)
            complexity = base * type_mult
        
        # Normalize: 0-30 range -> 0-1, then invert so lower complexity = higher score
        normalized = min(1.0, complexity / 30.0)
        return 1.0 - normalized  # Invert: simpler tests get higher scores
    
    def _evidence_confidence(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 6: Evidence Confidence
        
        Average confidence of enriched evidence references.
        Uses confidence from unified_model controls/pages if available.
        """
        enriched_evidence = test.metadata.get("enriched_evidence", [])
        if not enriched_evidence:
            return 0.0  # unknown
        
        confidences = []
        for ev in enriched_evidence:
            # Try to get confidence from entity properties
            conf = ev.get("confidence")
            if conf is not None:
                confidences.append(conf)
            else:
                # Default based on observation status
                status = ev.get("status", "unknown")
                confidences.append({"observed": 0.9, "inferred": 0.5, "unknown": 0.1}.get(status, 0.1))
        
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _cross_modal_evidence(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 7: Cross-Modal Evidence Coverage
        
        Fraction of evidence modalities present (dom, accessibility, visual, network).
        Each modality present adds 0.25.
        """
        modalities = set()
        enriched_evidence = test.metadata.get("enriched_evidence", [])
        
        for ev in enriched_evidence:
            ev_type = ev.get("type", "")
            if "dom" in ev_type.lower() or "page" in ev_type.lower():
                modalities.add("dom")
            elif "accessibility" in ev_type.lower() or "control" in ev_type.lower():
                modalities.add("accessibility")
            elif "visual" in ev_type.lower() or "screenshot" in ev_type.lower():
                modalities.add("visual")
            elif "network" in ev_type.lower() or "api" in ev_type.lower():
                modalities.add("network")
        
        # Also check page/control/form/api refs for modality hints
        if test.page_refs:
            modalities.add("dom")
        if test.control_refs:
            modalities.add("accessibility")
        if test.api_refs:
            modalities.add("network")
        
        return len(modalities) * 0.25  # 4 modalities max -> 1.0
    
    def _test_layer_signal(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 8: Test Layer/Type Signal
        
        Priority signal based on test_type and perspective.
        Higher priority layers (security, integration) get higher scores.
        """
        type_scores = {
            "SECURITY": 1.0,
            "INTEGRATION": 0.85,
            "PERFORMANCE": 0.8,
            "API": 0.65,
            "UI": 0.5,
            "UNIT": 0.3,
        }
        base = type_scores.get(test.test_type, 0.5)
        
        # Perspective boost: ENGINEERING tests often more technical
        if test.perspective == "ENGINEERING":
            base = min(1.0, base + 0.1)
        
        # Priority boost
        priority_boost = {"High": 0.15, "Medium": 0.05, "Low": 0.0}.get(test.priority, 0.0)
        
        return min(1.0, base + priority_boost)
    
    def _traceability_completeness(self, test: CandidateTest, context: Optional[EnrichmentContext]) -> float:
        """
        Feature 9: Traceability Completeness
        
        Fraction of all references (requirements, pages, controls, forms, apis, flows, evidence)
        that resolve to known entities in the knowledge model.
        """
        all_refs = (
            (test.requirement_refs or []) +
            (test.page_refs or []) +
            (test.control_refs or []) +
            (test.form_refs or []) +
            (test.api_refs or []) +
            (test.flow_refs or []) +
            (test.evidence_refs or [])
        )
        
        if not all_refs:
            return 0.0
        
        if not context or not context.knowledge_model:
            return 0.5  # inferred
        
        entity_ids = set()
        if context.knowledge_model.entities:
            entity_ids = {e.id for e in context.knowledge_model.entities}
        
        resolved = sum(1 for ref in all_refs if ref in entity_ids)
        return resolved / len(all_refs)


# Backward compatibility: wrapper that matches old TestFeatureExtractor interface
class LegacyFeatureExtractor:
    """Wrapper to maintain compatibility with existing Transformer ranker."""
    
    def __init__(self):
        self._extractor = Phase4FeatureExtractor()
    
    def extract(self, test: CandidateTest) -> np.ndarray:
        """Extract features in the old 9-feature format for backward compatibility."""
        # Map Phase 4 features to old feature positions
        fv = self._extractor.extract(test)
        features = fv.feature_values
        
        # Old features: [priority, test_type, perspective, risk_score, execution_cost, 
        #                historical_pass_rate, historical_failure_rate, coverage_gain, change_impact]
        # We'll map as best as possible:
        old_features = np.array([
            {"Low": 0.0, "Medium": 0.5, "High": 1.0}.get(test.priority, 0.5),  # priority
            {"UNIT": 0.1, "API": 0.3, "UI": 0.5, "INTEGRATION": 0.7, "SECURITY": 0.9, "PERFORMANCE": 1.0}.get(test.test_type, 0.5),  # test_type
            {"USER": 0.0, "ENGINEERING": 1.0}.get(test.perspective, 0.0),  # perspective
            test.risk_score,  # risk_score
            test.execution_cost / 10.0,  # execution_cost normalized
            test.historical_pass_rate,  # historical_pass_rate
            test.historical_failure_rate,  # historical_failure_rate
            test.coverage_gain,  # coverage_gain
            test.change_impact,  # change_impact
        ], dtype=np.float32)
        
        return old_features


__all__ = [
    "Phase4FeatureExtractor",
    "FeatureVector",
    "LegacyFeatureExtractor",
]