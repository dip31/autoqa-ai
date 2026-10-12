"""
Phase 4 — Test Enrichment Service.

Enriches CandidateTest objects with contextual information from the
Application Knowledge Model, Unified Application Model, and evidence sources.
"""

import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from agentqe.models.test_case import CandidateTest
from agentqe.models.context import ApplicationContext
from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result of enriching a single test."""
    test_id: str
    enriched: bool
    error: Optional[str] = None
    error_code: Optional[str] = None
    added_fields: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "enriched": self.enriched,
            "error": self.error,
            "error_code": self.error_code,
            "added_fields": self.added_fields,
        }


@dataclass
class EnrichmentContext:
    """Context available for enrichment."""
    app_context: Optional[ApplicationContext] = None
    knowledge_model: Optional[ApplicationKnowledgeModel] = None
    unified_model: Optional[Dict[str, Any]] = None
    rag_context: Optional[Dict[str, Any]] = None
    execution_history: Dict[str, Dict[str, float]] = field(default_factory=dict)
    repository_data: Dict[str, Any] = field(default_factory=dict)


class TestEnricher:
    """
    Enriches CandidateTest objects with contextual information.
    
    Enrichment adds:
    - Affected pages, controls, forms, API endpoints, modules, requirements, flows
    - Evidence references
    - Risk area references
    - Test layer/type signals
    - Authentication dependency
    - Destructive/action severity
    - Data dependency
    - Network dependency
    - Estimated execution complexity
    - Traceability completeness
    
    All enrichment uses observed/inferred/unknown semantics.
    """
    
    # Enrichment version for tracking
    ENRICHMENT_VERSION = "phase4-v1"
    
    def __init__(self):
        self._entity_cache: Dict[str, KnowledgeEntity] = {}
    
    def enrich(
        self,
        tests: List[CandidateTest],
        context: EnrichmentContext,
    ) -> List[CandidateTest]:
        """
        Enrich a list of CandidateTests.
        
        If enrichment fails for one test, the error is recorded on that test
        but other tests continue to be processed.
        """
        if not tests:
            return tests
        
        # Build entity cache for fast lookups
        self._build_entity_cache(context)
        
        results = []
        for test in tests:
            result = self._enrich_single(test, context)
            if result.error:
                logger.warning(f"Enrichment failed for {test.test_id}: {result.error}")
                # Attach error info to test metadata
                test.metadata["enrichment_error"] = result.error
                test.metadata["enrichment_error_code"] = result.error_code
            else:
                test.metadata["enriched"] = True
                test.metadata["enrichment_version"] = self.ENRICHMENT_VERSION
                test.metadata["enriched_fields"] = result.added_fields
            results.append(test)
        
        return results
    
    def _build_entity_cache(self, context: EnrichmentContext):
        """Build a cache of knowledge entities for fast lookup."""
        self._entity_cache = {}
        if context.knowledge_model and context.knowledge_model.entities:
            for entity in context.knowledge_model.entities:
                self._entity_cache[entity.id] = entity
    
    def _enrich_single(self, test: CandidateTest, context: EnrichmentContext) -> EnrichmentResult:
        """Enrich a single test."""
        added = []
        
        try:
            # Enrich with requirement references
            added.extend(self._enrich_requirements(test, context))
            
            # Enrich with page references
            added.extend(self._enrich_pages(test, context))
            
            # Enrich with control references
            added.extend(self._enrich_controls(test, context))
            
            # Enrich with form references
            added.extend(self._enrich_forms(test, context))
            
            # Enrich with API endpoint references
            added.extend(self._enrich_apis(test, context))
            
            # Enrich with flow references
            added.extend(self._enrich_flows(test, context))
            
            # Enrich with module references
            added.extend(self._enrich_modules(test, context))
            
            # Enrich with risk area references
            added.extend(self._enrich_risk_areas(test, context))
            
            # Enrich with evidence references
            added.extend(self._enrich_evidence(test, context))
            
            # Add test layer/type signals
            added.extend(self._enrich_test_signals(test, context))
            
            # Add authentication dependency
            added.extend(self._enrich_auth_dependency(test, context))
            
            # Add action severity
            added.extend(self._enrich_action_severity(test, context))
            
            # Add data dependency
            added.extend(self._enrich_data_dependency(test, context))
            
            # Add network dependency
            added.extend(self._enrich_network_dependency(test, context))
            
            # Add execution complexity
            added.extend(self._enrich_execution_complexity(test, context))
            
            # Add traceability completeness
            added.extend(self._enrich_traceability(test, context))
            
            # Deduplicate
            added = list(dict.fromkeys(added))
            
            return EnrichmentResult(test.test_id, enriched=True, added_fields=added)
            
        except Exception as e:
            logger.exception(f"Unexpected error enriching test {test.test_id}")
            return EnrichmentResult(
                test.test_id, 
                enriched=False, 
                error=str(e)[:300], 
                error_code="ENRICHMENT_ERROR"
            )
    
    def _enrich_requirements(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with requirement information."""
        added = []
        if test.requirement_refs:
            reqs = []
            for req_id in test.requirement_refs:
                entity = self._entity_cache.get(req_id)
                if entity:
                    reqs.append({
                        "id": entity.id,
                        "name": entity.name,
                        "status": entity.status,
                    })
                else:
                    reqs.append({"id": req_id, "status": "unknown"})
            test.metadata["enriched_requirements"] = reqs
            added.append("enriched_requirements")
        return added
    
    def _enrich_pages(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with page information."""
        added = []
        if test.page_refs:
            pages = []
            for page_id in test.page_refs:
                entity = self._entity_cache.get(page_id)
                if entity:
                    pages.append({
                        "id": entity.id,
                        "name": entity.name,
                        "url": entity.properties.get("url"),
                        "page_type": entity.properties.get("page_type"),
                        "status": entity.status,
                    })
                else:
                    pages.append({"id": page_id, "status": "unknown"})
            test.metadata["enriched_pages"] = pages
            added.append("enriched_pages")
        return added
    
    def _enrich_controls(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with control information."""
        added = []
        if test.control_refs:
            controls = []
            for ctrl_id in test.control_refs:
                entity = self._entity_cache.get(ctrl_id)
                if entity:
                    controls.append({
                        "id": entity.id,
                        "name": entity.name,
                        "type": entity.properties.get("type"),
                        "interactable": entity.properties.get("interactable", True),
                        "status": entity.status,
                    })
                else:
                    controls.append({"id": ctrl_id, "status": "unknown"})
            test.metadata["enriched_controls"] = controls
            added.append("enriched_controls")
        return added
    
    def _enrich_forms(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with form information."""
        added = []
        if test.form_refs:
            forms = []
            for form_id in test.form_refs:
                entity = self._entity_cache.get(form_id)
                if entity:
                    forms.append({
                        "id": entity.id,
                        "name": entity.name,
                        "method": entity.properties.get("method"),
                        "action": entity.properties.get("action"),
                        "fields": entity.properties.get("fields", []),
                        "status": entity.status,
                    })
                else:
                    forms.append({"id": form_id, "status": "unknown"})
            test.metadata["enriched_forms"] = forms
            added.append("enriched_forms")
        return added
    
    def _enrich_apis(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with API endpoint information."""
        added = []
        if test.api_refs:
            apis = []
            for api_id in test.api_refs:
                entity = self._entity_cache.get(api_id)
                if entity:
                    apis.append({
                        "id": entity.id,
                        "name": entity.name,
                        "method": entity.properties.get("method"),
                        "path": entity.properties.get("path"),
                        "status": entity.status,
                    })
                else:
                    apis.append({"id": api_id, "status": "unknown"})
            test.metadata["enriched_apis"] = apis
            added.append("enriched_apis")
        return added
    
    def _enrich_flows(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with user flow information."""
        added = []
        if test.flow_refs:
            flows = []
            for flow_id in test.flow_refs:
                entity = self._entity_cache.get(flow_id)
                if entity:
                    flows.append({
                        "id": entity.id,
                        "name": entity.name,
                        "source": entity.properties.get("source"),
                        "steps": entity.properties.get("steps", []),
                        "status": entity.status,
                    })
                else:
                    flows.append({"id": flow_id, "status": "unknown"})
            test.metadata["enriched_flows"] = flows
            added.append("enriched_flows")
        return added
    
    def _enrich_modules(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with module information."""
        added = []
        if context.knowledge_model and context.knowledge_model.entities:
            modules = [
                e for e in context.knowledge_model.entities 
                if e.entity_type == "module"
            ]
            if modules:
                test.metadata["available_modules"] = [
                    {"id": m.id, "name": m.name, "status": m.status} for m in modules
                ]
                added.append("available_modules")
        return added
    
    def _enrich_risk_areas(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with risk area references."""
        added = []
        if context.unified_model and context.unified_model.get("risk_areas"):
            risk_areas = context.unified_model["risk_areas"]
            # Match test to risk areas based on page/control/module overlap
            matched_risks = []
            test_pages = set(test.page_refs)
            test_controls = set(test.control_refs)
            
            for risk in risk_areas:
                risk_pages = set(risk.get("pages", []))
                risk_controls = set(risk.get("controls", []))
                
                if test_pages & risk_pages or test_controls & risk_controls:
                    matched_risks.append({
                        "id": risk.get("id"),
                        "name": risk.get("name"),
                        "severity": risk.get("severity", "medium"),
                        "description": risk.get("description", ""),
                    })
            
            if matched_risks:
                test.metadata["matched_risk_areas"] = matched_risks
                added.append("matched_risk_areas")
        return added
    
    def _enrich_evidence(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Enrich with evidence references."""
        added = []
        evidence_refs = test.evidence_refs or []
        if evidence_refs:
            enriched_evidence = []
            for ev_id in evidence_refs:
                entity = self._entity_cache.get(ev_id)
                if entity:
                    enriched_evidence.append({
                        "id": entity.id,
                        "type": entity.entity_type,
                        "name": entity.name,
                        "status": entity.status,
                    })
                else:
                    enriched_evidence.append({"id": ev_id, "status": "unknown"})
            test.metadata["enriched_evidence"] = enriched_evidence
            added.append("enriched_evidence")
        return added
    
    def _enrich_test_signals(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add test layer/type signals."""
        added = []
        test.metadata["test_layer"] = test.test_type
        test.metadata["test_perspective"] = test.perspective
        test.metadata["source_agent"] = test.source_agent
        added.extend(["test_layer", "test_perspective", "source_agent"])
        return added
    
    def _enrich_auth_dependency(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add authentication dependency information."""
        added = []
        # Check if any referenced pages require auth
        requires_auth = False
        auth_pages = []
        
        for page_id in test.page_refs:
            entity = self._entity_cache.get(page_id)
            if entity and entity.properties.get("requires_auth"):
                requires_auth = True
                auth_pages.append(entity.id)
        
        test.metadata["requires_authentication"] = requires_auth
        test.metadata["auth_pages"] = auth_pages
        added.extend(["requires_authentication", "auth_pages"])
        return added
    
    def _enrich_action_severity(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add action severity (destructive vs read-only)."""
        added = []
        # Heuristic: check steps for destructive keywords
        destructive_keywords = ["delete", "remove", "drop", "truncate", "destroy", "purge"]
        steps_text = " ".join(test.steps).lower()
        is_destructive = any(kw in steps_text for kw in destructive_keywords)
        
        test.metadata["action_severity"] = "destructive" if is_destructive else "read_only"
        added.append("action_severity")
        return added
    
    def _enrich_data_dependency(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add data dependency information."""
        added = []
        # Check if test requires specific data setup
        data_keywords = ["create", "insert", "add", "setup", "seed", "fixture"]
        steps_text = " ".join(test.steps).lower()
        has_data_dependency = any(kw in steps_text for kw in data_keywords)
        
        test.metadata["data_dependency"] = "required" if has_data_dependency else "none"
        added.append("data_dependency")
        return added
    
    def _enrich_network_dependency(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add network dependency information."""
        added = []
        # Check if test references API endpoints
        has_network_deps = bool(test.api_refs)
        
        test.metadata["network_dependency"] = "required" if has_network_deps else "none"
        added.append("network_dependency")
        return added
    
    def _enrich_execution_complexity(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add estimated execution complexity."""
        added = []
        # Complexity based on steps, test type, and dependencies
        base_complexity = len(test.steps)
        
        type_multiplier = {
            "UNIT": 1.0,
            "API": 1.5,
            "UI": 2.5,
            "INTEGRATION": 3.0,
            "SECURITY": 3.5,
            "PERFORMANCE": 4.0,
        }.get(test.test_type, 2.0)
        
        complexity = round(base_complexity * type_multiplier, 1)
        test.metadata["estimated_complexity"] = complexity
        test.metadata["complexity_tier"] = (
            "low" if complexity < 5 else 
            "medium" if complexity < 15 else 
            "high"
        )
        added.extend(["estimated_complexity", "complexity_tier"])
        return added
    
    def _enrich_traceability(self, test: CandidateTest, context: EnrichmentContext) -> List[str]:
        """Add traceability completeness score."""
        added = []
        # Traceability = fraction of refs that resolve to known entities
        all_refs = (
            test.requirement_refs + test.page_refs + test.control_refs + 
            test.form_refs + test.api_refs + test.flow_refs + test.evidence_refs
        )
        
        if all_refs:
            resolved = sum(1 for r in all_refs if r in self._entity_cache)
            traceability = round(resolved / len(all_refs), 2)
        else:
            traceability = 0.0
        
        test.metadata["traceability_completeness"] = traceability
        test.metadata["traceability_tier"] = (
            "complete" if traceability >= 0.8 else
            "partial" if traceability >= 0.4 else
            "minimal"
        )
        added.extend(["traceability_completeness", "traceability_tier"])
        return added


# Backward compatibility with existing enricher
class LegacyTestEnricher:
    """Wrapper to maintain backward compatibility with Phase 3 enricher."""
    
    def __init__(self):
        self._enricher = TestEnricher()
    
    def enrich(self, tests, execution_history=None, repository_data=None):
        context = EnrichmentContext(
            execution_history=execution_history or {},
            repository_data=repository_data or {},
        )
        return self._enricher.enrich(tests, context)


__all__ = [
    "TestEnricher",
    "EnrichmentContext",
    "EnrichmentResult",
    "LegacyTestEnricher",
]