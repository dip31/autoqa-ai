"""
Phase 4 — Test Prioritization Tests.

Tests for enrichment, feature extraction, bootstrap ranking, and API.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from agentqe.models.test_case import CandidateTest
from agentqe.models.context import ApplicationContext
from agentqe.enrichment.service import TestEnricher, EnrichmentContext, EnrichmentResult
from agentqe.prioritization.feature_extractor import Phase4FeatureExtractor, FeatureVector
from agentqe.prioritization.bootstrap_ranker import BootstrapRanker, RankingWeights, RankedTest
from agentqe.prioritization.service import TestPrioritizationService, PrioritizationResult


@pytest.fixture
def auth_headers(client):
    """Get JWT auth headers by registering and logging in a test user."""
    # Register a test user
    register_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
        "role": "qa_engineer"
    }
    client.post("/auth/register", json=register_data)
    
    # Login to get token
    login_resp = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpass123"
    })
    token = login_resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestPhase4FeatureExtractor:
    """Tests for Phase 4 feature extractor."""
    
    def test_extracts_exactly_9_features(self):
        """Feature extractor must produce exactly 9 features."""
        test = CandidateTest(
            test_id="TC-001",
            title="Test Login",
            description="Verify login works",
            test_type="UI",
            priority="High",
            perspective="USER",
            steps=["Go to login", "Enter credentials", "Click login"],
        )
        
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test)
        
        assert len(fv.feature_names) == 9
        assert len(fv.feature_values) == 9
        assert fv.feature_version == "phase4-v1"
    
    def test_feature_names_match_spec(self):
        """Feature names must match the documented 9 features."""
        extractor = Phase4FeatureExtractor()
        expected = [
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
        assert extractor.FEATURE_NAMES == expected
    
    def test_features_normalized_0_1(self):
        """All features must be normalized to [0, 1]."""
        test = CandidateTest(
            test_id="TC-001",
            title="Test Login",
            test_type="SECURITY",
            priority="High",
            perspective="ENGINEERING",
            steps=["step"] * 20,  # Many steps = high complexity
        )
        
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test)
        
        for val in fv.feature_values:
            assert 0.0 <= val <= 1.0, f"Feature value {val} not in [0,1]"
    
    def test_deterministic_same_input_same_output(self):
        """Same test must produce identical feature vectors."""
        test = CandidateTest(
            test_id="TC-001",
            title="Test Login",
            test_type="UI",
            priority="Medium",
            steps=["step1", "step2"],
        )
        
        extractor = Phase4FeatureExtractor()
        fv1 = extractor.extract(test)
        fv2 = extractor.extract(test)
        
        assert fv1.feature_values == fv2.feature_values
    
    def test_requirement_relevance_with_refs(self):
        """Requirement relevance should be >0 when requirement_refs exist."""
        from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity
        
        test = CandidateTest(
            test_id="TC-001",
            title="Test Login",
            requirement_refs=["req:login"],
        )
        
        knowledge_model = ApplicationKnowledgeModel(entities=[
            KnowledgeEntity(id="req:login", entity_type="requirement", name="Login Req", properties={"priority": "High"})
        ])
        
        context = EnrichmentContext(knowledge_model=knowledge_model)
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test, context)
        
        # requirement_relevance is first feature
        assert fv.feature_values[0] > 0.0
    
    def test_risk_relevance_with_matched_risks(self):
        """Risk relevance should be >0 when matched_risk_areas in metadata."""
        test = CandidateTest(
            test_id="TC-001",
            title="Test Login",
            metadata={"matched_risk_areas": [{"severity": "High"}, {"severity": "Critical"}]},
        )
        
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test)
        
        # risk_relevance is second feature
        assert fv.feature_values[1] > 0.0
    
    def test_execution_complexity_inverted(self):
        """Execution complexity should be inverted (simpler = higher score)."""
        simple_test = CandidateTest(test_id="TC-001", title="Simple", test_type="UNIT", steps=["step"])
        complex_test = CandidateTest(test_id="TC-002", title="Complex", test_type="UI", steps=["step"] * 30)
        
        extractor = Phase4FeatureExtractor()
        simple_fv = extractor.extract(simple_test)
        complex_fv = extractor.extract(complex_test)
        
        # execution_complexity is 5th feature (index 4)
        # Simpler test should have higher score (since inverted)
        assert simple_fv.feature_values[4] > complex_fv.feature_values[4]
    
    def test_cross_modal_evidence_max_1(self):
        """Cross-modal evidence should max at 1.0 (4 modalities * 0.25)."""
        test = CandidateTest(
            test_id="TC-001",
            title="Test",
            metadata={"enriched_evidence": [
                {"type": "dom"},
                {"type": "accessibility"},
                {"type": "visual"},
                {"type": "network"},
            ]},
        )
        
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test)
        
        # cross_modal_evidence is 7th feature (index 6)
        assert fv.feature_values[6] == 1.0
    
    def test_traceability_completeness(self):
        """Traceability completeness should be fraction of resolvable refs."""
        from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity
        
        test = CandidateTest(
            test_id="TC-001",
            title="Test",
            requirement_refs=["req:1", "req:2"],
            page_refs=["page:1"],
        )
        
        knowledge_model = ApplicationKnowledgeModel(entities=[
            KnowledgeEntity(id="req:1", entity_type="requirement", name="Req 1"),
            KnowledgeEntity(id="page:1", entity_type="page", name="Page 1"),
            # req:2 missing
        ])
        
        context = EnrichmentContext(knowledge_model=knowledge_model)
        extractor = Phase4FeatureExtractor()
        fv = extractor.extract(test, context)
        
        # traceability_completeness is 9th feature (index 8)
        # 2 out of 3 refs resolvable = 0.666...
        assert abs(fv.feature_values[8] - 2/3) < 0.01


class TestBootstrapRanker:
    """Tests for deterministic bootstrap ranker."""
    
    def test_weights_sum_to_one(self):
        """Ranking weights must sum to 1.0."""
        weights = RankingWeights()
        assert abs(sum(weights.weights) - 1.0) < 0.001
    
    def test_exactly_9_weights(self):
        """Must have exactly 9 weights."""
        weights = RankingWeights()
        assert len(weights.weights) == 9
    
    def test_deterministic_ranking(self):
        """Same inputs must produce same ranking order."""
        tests = [
            CandidateTest(test_id="TC-001", title="Test 1", test_type="UI", priority="High", steps=["s1", "s2"]),
            CandidateTest(test_id="TC-002", title="Test 2", test_type="API", priority="Medium", steps=["s1"]),
            CandidateTest(test_id="TC-003", title="Test 3", test_type="UNIT", priority="Low", steps=["s1", "s2", "s3"]),
        ]
        
        ranker = BootstrapRanker()
        ranked1 = ranker.rank(tests)
        ranked2 = ranker.rank(tests)
        
        # Same order
        assert [r.test.test_id for r in ranked1] == [r.test.test_id for r in ranked2]
        # Same scores
        for r1, r2 in zip(ranked1, ranked2):
            assert r1.bootstrap_score == r2.bootstrap_score
            assert r1.rank == r2.rank
    
    def test_ranking_mode_bootstrap(self):
        """Ranking mode must be 'bootstrap'."""
        tests = [CandidateTest(test_id="TC-001", title="Test", test_type="UI")]
        ranker = BootstrapRanker()
        ranked = ranker.rank(tests)
        
        assert ranked[0].ranking_mode == "bootstrap"
        assert ranked[0].model_status == "untrained"
    
    def test_explanation_generated(self):
        """Every ranked test must have an explanation."""
        tests = [CandidateTest(test_id="TC-001", title="Test Security", test_type="SECURITY", priority="High")]
        ranker = BootstrapRanker()
        ranked = ranker.rank(tests)
        
        assert ranked[0].explanation
        assert len(ranked[0].explanation) > 0
    
    def test_feature_contributions_sum_to_score(self):
        """Feature contributions should sum to bootstrap score (approximately)."""
        tests = [CandidateTest(test_id="TC-001", title="Test", test_type="UI", priority="High")]
        ranker = BootstrapRanker()
        ranked = ranker.rank(tests)
        
        contrib_sum = sum(ranked[0].feature_contributions.values())
        assert abs(contrib_sum - ranked[0].bootstrap_score) < 0.001
    
    def test_high_priority_requirements_rank_higher(self):
        """Tests with high requirement relevance should rank higher."""
        from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity
        
        test_high = CandidateTest(test_id="TC-001", title="High Req", requirement_refs=["req:1"])
        test_low = CandidateTest(test_id="TC-002", title="Low Req", requirement_refs=[])
        
        knowledge_model = ApplicationKnowledgeModel(entities=[
            KnowledgeEntity(id="req:1", entity_type="requirement", name="Req 1", properties={"priority": "High"})
        ])
        
        context = EnrichmentContext(knowledge_model=knowledge_model)
        ranker = BootstrapRanker()
        
        ranked = ranker.rank([test_high, test_low], context)
        
        # High requirement test should rank higher (or at least not lower)
        assert ranked[0].test.test_id == "TC-001"


class TestTestEnricher:
    """Tests for TestEnricher."""
    
    def test_enrichment_preserves_observed_inferred_unknown(self):
        """Enrichment must use observed/inferred/unknown semantics."""
        from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity
        
        test = CandidateTest(test_id="TC-001", title="Test", requirement_refs=["req:1", "req:unknown"])
        knowledge_model = ApplicationKnowledgeModel(entities=[
            KnowledgeEntity(id="req:1", entity_type="requirement", name="Req 1", status="observed")
        ])
        
        context = EnrichmentContext(knowledge_model=knowledge_model)
        enricher = TestEnricher()
        enriched = enricher.enrich([test], context)
        
        enriched_test = enriched[0]
        reqs = enriched_test.metadata.get("enriched_requirements", [])
        
        # req:1 should be observed
        observed_req = next((r for r in reqs if r["id"] == "req:1"), None)
        assert observed_req is not None
        assert observed_req["status"] == "observed"
        
        # req:unknown should be unknown
        unknown_req = next((r for r in reqs if r["id"] == "req:unknown"), None)
        assert unknown_req is not None
        assert unknown_req["status"] == "unknown"
    
    def test_enrichment_failure_isolation(self):
        """Enrichment failure for one test should not fail others."""
        from agentqe.enrichment.service import TestEnricher, EnrichmentResult
        from unittest.mock import patch
        
        test1 = CandidateTest(test_id="TC-001", title="Test 1")
        test2 = CandidateTest(test_id="TC-002", title="Test 2")
        
        enricher = TestEnricher()
        
        # Store original method
        original_enrich_single = enricher._enrich_single
        
        def mock_enrich_single(test, ctx):
            if test.test_id == "TC-002":
                return EnrichmentResult(test.test_id, enriched=False, error="Simulated enrichment error", error_code="ENRICHMENT_ERROR")
            # For test1, call the original method
            return original_enrich_single(test, ctx)
        
        # Replace the method
        enricher._enrich_single = mock_enrich_single
        
        try:
            enriched = enricher.enrich([test1, test2], EnrichmentContext())
        finally:
            # Restore original method
            enricher._enrich_single = original_enrich_single
        
        # test1 should be enriched
        assert enriched[0].metadata.get("enriched") is True
        # test2 should have error metadata
        assert "enrichment_error" in enriched[1].metadata
    
    def test_enrichment_adds_expected_fields(self):
        """Enrichment should add expected metadata fields."""
        test = CandidateTest(test_id="TC-001", title="Test", test_type="UI", steps=["step"])
        
        enricher = TestEnricher()
        enriched = enricher.enrich([test], EnrichmentContext())
        
        enriched_test = enriched[0]
        # Check for key enrichment fields
        assert "enrichment_version" in enriched_test.metadata
        assert "traceability_completeness" in enriched_test.metadata
        assert "estimated_complexity" in enriched_test.metadata
        assert "action_severity" in enriched_test.metadata
        assert "requires_authentication" in enriched_test.metadata


class TestPrioritizationServiceTests:
    """Tests for TestPrioritizationService."""
    
    def test_prioritize_empty_list(self):
        """Prioritizing empty list should return empty result."""
        from agentqe.prioritization.service import TestPrioritizationService
        service = TestPrioritizationService()
        result = service.prioritize([])
        
        assert isinstance(result, PrioritizationResult)
        assert result.total_tests == 0
        assert result.ranked_tests == []
    
    def test_prioritize_returns_metadata(self):
        """Prioritization result must include ranking metadata."""
        from agentqe.prioritization.service import TestPrioritizationService
        tests = [CandidateTest(test_id="TC-001", title="Test", test_type="UI")]
        service = TestPrioritizationService()
        result = service.prioritize(tests)
        
        assert result.ranking_mode in ("bootstrap", "transformer")
        assert result.model_status in ("trained", "untrained")
        assert result.feature_version == "phase4-v1"
    
    def test_get_ranking_metadata(self):
        """get_ranking_metadata should return configuration."""
        from agentqe.prioritization.service import TestPrioritizationService
        service = TestPrioritizationService()
        meta = service.get_ranking_metadata()
        
        assert "ranking_mode" in meta
        assert "model_status" in meta
        assert "bootstrap_weights" in meta
        assert "feature_names" in meta
        assert len(meta["feature_names"]) == 9
    
    def test_deterministic_full_pipeline(self):
        """Full pipeline must be deterministic."""
        from agentqe.prioritization.service import TestPrioritizationService
        tests = [
            CandidateTest(test_id="TC-001", title="Test 1", test_type="UI", priority="High", steps=["s1"]),
            CandidateTest(test_id="TC-002", title="Test 2", test_type="API", priority="Medium", steps=["s1", "s2"]),
        ]
        
        service = TestPrioritizationService()
        result1 = service.prioritize(tests)
        result2 = service.prioritize(tests)
        
        # Same order
        assert [r.test.test_id for r in result1.ranked_tests] == [r.test.test_id for r in result2.ranked_tests]
        # Same scores
        for r1, r2 in zip(result1.ranked_tests, result2.ranked_tests):
            assert r1.bootstrap_score == r2.bootstrap_score
            assert r1.feature_vector.feature_values == r2.feature_vector.feature_values


class TestPhase4API:
    """Tests for Phase 4 API endpoint."""

    def test_prioritize_endpoint_deserializes_knowledge_model(self, client, auth_headers):
        """Serialized knowledge entities must be model instances before prioritization."""
        with patch("agentqe.prioritization.service.TestPrioritizationService") as service_class:
            result = MagicMock()
            result.to_dict.return_value = {
                "ranked_tests": [],
                "enrichment_summary": {"total": 1, "enriched": 1, "failed": 0},
                "ranking_metadata": {},
            }
            service_class.return_value.prioritize.return_value = result

            response = client.post(
                "/api/agentqe/tests/prioritize",
                json={
                    "candidate_tests": [{"test_id": "TC-001", "title": "Test"}],
                    "knowledge_model": {
                        "entities": [
                            {"id": "requirement:login", "entity_type": "requirement", "name": "Login"}
                        ],
                        "relationships": [],
                    },
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        model = service_class.return_value.prioritize.call_args.kwargs["knowledge_model"]
        assert model.entities[0].id == "requirement:login"
        assert not isinstance(model.entities[0], dict)
    
    def test_prioritize_endpoint_requires_auth(self, client):
        """POST without auth should return 401."""
        resp = client.post("/api/agentqe/tests/prioritize", json={})
        assert resp.status_code == 401
    
    def test_prioritize_endpoint_requires_candidate_tests(self, client, auth_headers):
        """POST without candidate_tests should return 400."""
        resp = client.post("/api/agentqe/tests/prioritize", 
                          json={},
                          headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "candidate_tests is required" in data["error"]
    
    @patch("agentqe.prioritization.service.TestPrioritizationService")
    @patch("agentqe.models.test_case.CandidateTest")
    def test_prioritize_endpoint_success(self, mock_candidate_test_class, mock_service_class, client, auth_headers):
        """Successful prioritization should return ranked tests."""
        # Mock the CandidateTest constructor
        mock_test_instance = MagicMock()
        mock_test_instance.to_dict.return_value = {"test_id": "TC-001", "title": "Test"}
        mock_candidate_test_class.return_value = mock_test_instance
        
        # Mock the service
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "ranked_tests": [{
                "test": {"test_id": "TC-001", "title": "Test"},
                "bootstrap_score": 0.85,
                "rank": 1,
                "ranking_mode": "bootstrap",
                "model_status": "untrained",
                "explanation": "High priority test",
                "feature_contributions": {"requirement_relevance": 0.2},
            }],
            "enrichment_summary": {"total": 1, "enriched": 1, "failed": 0},
            "ranking_metadata": {
                "ranking_mode": "bootstrap",
                "model_status": "untrained",
                "model_version": "phase4-v1",
                "feature_version": "phase4-v1",
            },
        }
        mock_service.prioritize.return_value = mock_result
        mock_service_class.return_value = mock_service
        
        resp = client.post("/api/agentqe/tests/prioritize",
                          json={"candidate_tests": [{"test_id": "TC-001", "title": "Test"}]},
                          headers=auth_headers)
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "ranked_tests" in data
        assert len(data["ranked_tests"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])