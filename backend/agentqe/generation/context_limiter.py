"""
Bounded context builder with relevance ranking and token budget enforcement.

Replaces the unlimited context dump with a compact, relevance-filtered context
that stays within the configured token budget.
"""

import logging
import re
from typing import Dict, Any, List, Set, Tuple, Optional
from collections import defaultdict

from agentqe.models.context import ApplicationContext
from .config import ContextBudgetConfig, resolve_context_budget
from .schemas import GenerationContext

# Optional RAG import
try:
    from agentqe.rag.service import RAGService
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    RAGService = None

logger = logging.getLogger(__name__)


class BoundedContextBuilder:
    """
    Builds compact, relevance-filtered generation context within token budget.
    
    Strategy:
    1. Rank entities by relevance to requirement
    2. Apply per-entity type limits
    3. Serialize compactly
    4. Estimate tokens
    5. Reduce if over budget
    """
    
    def __init__(self, rag_service: RAGService = None, budget_config: ContextBudgetConfig = None):
        self.rag = rag_service
        self.budget_config = budget_config or resolve_context_budget()
    
    def build(self, app_context: ApplicationContext, requirement: str, agent_type: str = "user") -> Dict[str, Any]:
        """
        Build bounded generation context for a specific agent type.
        
        Args:
            app_context: Application context with knowledge model
            requirement: The requirement to generate tests for
            agent_type: "user" or "engineering" - determines context focus
        
        Returns:
            Bounded generation context dictionary
        """
        km = app_context.knowledge_model or {}
        entities = km.get("entities", [])
        
        # Extract entities by type
        all_pages = [e for e in entities if e.get("entity_type") == "page"]
        all_controls = [e for e in entities if e.get("entity_type") == "control"]
        all_forms = [e for e in entities if e.get("entity_type") == "form"]
        all_apis = [e for e in entities if e.get("entity_type") == "api_endpoint"]
        all_flows = [e for e in entities if e.get("entity_type") == "user_flow"]
        all_modules = [e for e in entities if e.get("entity_type") == "module"]
        
        # RAG retrieval
        retrieved_documents = []
        evidence_refs = set()
        if self.rag and self.rag.is_ready and requirement:
            try:
                results = self.rag.query(requirement, top_k=self.budget_config.rag_top_k)
                for r in results:
                    retrieved_documents.append(r.to_dict())
                    for ref in r.evidence_refs:
                        evidence_refs.add(ref)
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")
        
        # Rank entities by relevance
        ranked_pages = self._rank_entities(all_pages, requirement, agent_type)
        ranked_controls = self._rank_entities(all_controls, requirement, agent_type)
        ranked_forms = self._rank_entities(all_forms, requirement, agent_type)
        ranked_apis = self._rank_entities(all_apis, requirement, agent_type)
        ranked_flows = self._rank_entities(all_flows, requirement, agent_type)
        ranked_modules = self._rank_entities(all_modules, requirement, agent_type)
        
        # Apply per-entity limits
        pages = ranked_pages[:self.budget_config.max_pages]
        controls = ranked_controls[:self.budget_config.max_controls]
        forms = ranked_forms[:self.budget_config.max_forms]
        apis = ranked_apis[:self.budget_config.max_apis]
        flows = ranked_flows[:self.budget_config.max_flows]
        modules = ranked_modules[:self.budget_config.max_modules]
        
        # Extract evidence refs from selected entities
        for entity_list in [pages, controls, forms, apis, flows, modules]:
            for e in entity_list:
                for ref in e.get("evidence_refs", []):
                    evidence_refs.add(ref)
        
        # Build compact context
        ctx = GenerationContext(
            requirement=requirement,
            pages=pages,
            controls=controls,
            forms=forms,
            apis=apis,
            flows=flows,
            modules=modules,
            repository_context=self._compact_repo_context(app_context.repository_data or {}),
            retrieved_documents=retrieved_documents[:self.budget_config.max_evidence_items],
            evidence_refs=list(evidence_refs)
        )
        
        # Serialize compactly
        compact_ctx = self._serialize_compact(ctx.to_dict(), agent_type)
        
        # Estimate tokens and reduce if needed
        final_ctx = self._enforce_token_budget(compact_ctx, agent_type)
        
        return final_ctx
    
    def _rank_entities(self, entities: List[Dict], requirement: str, agent_type: str) -> List[Dict]:
        """
        Rank entities by relevance to requirement.
        
        Relevance signals:
        - Text overlap with requirement
        - Direct traceability to requirement
        - Module association
        - Risk association
        - RAG similarity score (if available)
        """
        if not entities:
            return []
        
        req_lower = requirement.lower()
        scored_entities = []
        
        for entity in entities:
            score = 0.0
            
            # Text overlap in name/description
            name = entity.get("name", "").lower()
            description = entity.get("description", "").lower()
            
            # Direct name match
            if req_lower in name:
                score += 2.0
            
            # Partial name match
            for word in req_lower.split():
                if word in name:
                    score += 0.5
            
            # Description match
            if req_lower in description:
                score += 1.0
            
            # Requirement traceability
            req_refs = entity.get("requirement_refs", [])
            for ref in req_refs:
                if ref.lower() in req_lower:
                    score += 1.5
            
            # Module association
            module = entity.get("module", "")
            if module and module.lower() in req_lower:
                score += 0.5
            
            # Risk association
            risk_refs = entity.get("risk_refs", [])
            if risk_refs:
                score += 0.3
            
            # Agent-type specific boosts
            if agent_type == "user":
                # User agent prefers pages, flows, controls
                if entity.get("entity_type") in ["page", "user_flow", "control"]:
                    score += 0.5
                # Deprioritize APIs
                if entity.get("entity_type") == "api_endpoint":
                    score -= 0.3
            elif agent_type == "engineering":
                # Engineering agent prefers APIs, forms, modules
                if entity.get("entity_type") in ["api_endpoint", "form", "module"]:
                    score += 0.5
                # Deprioritize unrelated UI elements
                if entity.get("entity_type") == "control" and "button" not in name:
                    score -= 0.2
            
            scored_entities.append((score, entity))
        
        # Sort by score descending
        scored_entities.sort(key=lambda x: x[0], reverse=True)
        
        return [entity for score, entity in scored_entities]
    
    def _compact_repo_context(self, repo_context: Dict) -> Dict:
        """
        Compact repository context to essential information only.
        """
        if not repo_context:
            return {}
        
        compact = {}
        
        # Limit files
        files = repo_context.get("files", [])
        if files:
            compact["files"] = files[:self.budget_config.max_repo_files]
        
        # Limit symbols
        symbols = repo_context.get("symbols", [])
        if symbols:
            compact["symbols"] = symbols[:self.budget_config.max_repo_symbols]
        
        # Keep module structure but compacted
        if "modules" in repo_context:
            compact["modules"] = repo_context["modules"][:self.budget_config.max_modules]
        
        return compact
    
    def _serialize_compact(self, ctx: Dict, agent_type: str) -> Dict:
        """
        Serialize context in compact text format instead of full JSON.
        """
        compact = {
            "requirement": ctx.get("requirement", ""),
        }
        
        # Compact pages
        if ctx.get("pages"):
            compact["pages"] = self._compact_entities(ctx["pages"], "page")
        
        # Compact controls
        if ctx.get("controls"):
            compact["controls"] = self._compact_entities(ctx["controls"], "control")
        
        # Compact forms
        if ctx.get("forms"):
            compact["forms"] = self._compact_entities(ctx["forms"], "form")
        
        # Compact APIs
        if ctx.get("apis"):
            compact["apis"] = self._compact_entities(ctx["apis"], "api")
        
        # Compact flows
        if ctx.get("flows"):
            compact["flows"] = self._compact_entities(ctx["flows"], "flow")
        
        # Compact modules
        if ctx.get("modules"):
            compact["modules"] = self._compact_entities(ctx["modules"], "module")
        
        # Compact repo context
        if ctx.get("repository_context"):
            compact["repository_context"] = ctx["repository_context"]
        
        # Compact RAG docs (already compact from RAG)
        if ctx.get("retrieved_documents"):
            compact["rag_docs"] = ctx["retrieved_documents"]
        
        return compact
    
    def _compact_entities(self, entities: List[Dict], entity_type: str) -> List[str]:
        """
        Convert entities to compact string representations.
        """
        compact = []
        for e in entities:
            name = e.get("name", e.get("id", "unknown"))
            
            if entity_type == "page":
                url = e.get("url", e.get("path", ""))
                purpose = e.get("description", "")[:50]
                compact.append(f"{name} ({url}) - {purpose}")
            
            elif entity_type == "control":
                page = e.get("page_ref", "")
                control_type = e.get("control_type", "")
                compact.append(f"{name} on {page} ({control_type})")
            
            elif entity_type == "form":
                page = e.get("page_ref", "")
                fields = e.get("fields", [])
                field_names = ", ".join(f.get("name", "") for f in fields[:3])
                compact.append(f"{name} on {page} - fields: {field_names}")
            
            elif entity_type == "api":
                method = e.get("method", "GET")
                path = e.get("path", "")
                compact.append(f"{method} {path}")
            
            elif entity_type == "flow":
                steps = e.get("steps", [])
                step_count = len(steps)
                compact.append(f"{name} ({step_count} steps)")
            
            elif entity_type == "module":
                compact.append(name)
            
            else:
                compact.append(name)
        
        return compact
    
    def _enforce_token_budget(self, ctx: Dict, agent_type: str) -> Dict:
        """
        Estimate tokens and reduce context if over budget.
        """
        # Estimate token count
        estimated_tokens = self._estimate_tokens(ctx)
        
        logger.info(
            f"[AgentQE Generation] agent={agent_type} "
            f"estimated_prompt_tokens={estimated_tokens} "
            f"budget={self.budget_config.max_prompt_tokens}"
        )
        
        if estimated_tokens <= self.budget_config.max_prompt_tokens:
            return ctx
        
        # Over budget - reduce context
        logger.warning(
            f"Context over budget ({estimated_tokens} > {self.budget_config.max_prompt_tokens}), "
            f"applying reduction strategy"
        )
        
        # Reduction strategy
        reduced_ctx = self._reduce_context(ctx, agent_type)
        
        # Re-check
        reduced_tokens = self._estimate_tokens(reduced_ctx)
        logger.info(f"After reduction: {reduced_tokens} tokens")
        
        return reduced_ctx
    
    def _estimate_tokens(self, ctx: Dict) -> int:
        """
        Estimate token count using a conservative heuristic.
        
        Approximation: 1 token ≈ 4 characters for English text.
        This is conservative and may overestimate slightly.
        """
        text = str(ctx)
        # Remove whitespace for more accurate count
        text = re.sub(r'\s+', ' ', text)
        # Conservative estimate: 1 token per 3.5 characters
        return int(len(text) / 3.5)
    
    def _reduce_context(self, ctx: Dict, agent_type: str) -> Dict:
        """
        Apply reduction strategy to fit within budget.
        
        Strategy:
        1. Remove RAG docs
        2. Reduce repository context
        3. Reduce controls
        4. Reduce pages
        5. Reduce flows/APIs
        """
        reduced = ctx.copy()
        
        # Step 1: Remove RAG docs
        if "rag_docs" in reduced:
            del reduced["rag_docs"]
            if self._estimate_tokens(reduced) <= self.budget_config.max_prompt_tokens:
                return reduced
        
        # Step 2: Reduce repository context
        if "repository_context" in reduced:
            reduced["repository_context"] = {}
            if self._estimate_tokens(reduced) <= self.budget_config.max_prompt_tokens:
                return reduced
        
        # Step 3: Reduce controls by half
        if "controls" in reduced and len(reduced["controls"]) > 5:
            reduced["controls"] = reduced["controls"][:5]
            if self._estimate_tokens(reduced) <= self.budget_config.max_prompt_tokens:
                return reduced
        
        # Step 4: Reduce pages by half
        if "pages" in reduced and len(reduced["pages"]) > 5:
            reduced["pages"] = reduced["pages"][:5]
            if self._estimate_tokens(reduced) <= self.budget_config.max_prompt_tokens:
                return reduced
        
        # Step 5: Reduce flows/APIs
        if agent_type == "user" and "flows" in reduced:
            reduced["flows"] = reduced["flows"][:3]
        elif agent_type == "engineering" and "apis" in reduced:
            reduced["apis"] = reduced["apis"][:5]
        
        return reduced


__all__ = ["BoundedContextBuilder"]
