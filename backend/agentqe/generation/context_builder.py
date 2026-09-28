import logging
from typing import Dict, Any, List

from agentqe.models.context import ApplicationContext
from agentqe.rag.service import RAGService
from .interfaces import IContextBuilder
from .schemas import GenerationContext

logger = logging.getLogger(__name__)

class DeterministicContextBuilder(IContextBuilder):
    def __init__(self, rag_service: RAGService):
        self.rag = rag_service
        
    def build(self, app_context: ApplicationContext, requirement: str) -> Dict[str, Any]:
        retrieved_documents = []
        evidence_refs = set()
        
        # 1. RAG Retrieval if available
        if self.rag and self.rag.is_ready and requirement:
            try:
                results = self.rag.query(requirement, top_k=10)
                for r in results:
                    retrieved_documents.append(r.to_dict())
                    for ref in r.evidence_refs:
                        evidence_refs.add(ref)
            except Exception as e:
                logger.warning(f"RAG retrieval failed during context building: {e}")

        # 2. Add deterministic context from Knowledge Model
        km = app_context.knowledge_model or {}
        entities = km.get("entities", [])
        
        pages = [e for e in entities if e.get("entity_type") == "page"]
        controls = [e for e in entities if e.get("entity_type") == "control"]
        forms = [e for e in entities if e.get("entity_type") == "form"]
        apis = [e for e in entities if e.get("entity_type") == "api_endpoint"]
        flows = [e for e in entities if e.get("entity_type") == "user_flow"]
        modules = [e for e in entities if e.get("entity_type") == "module"]
        
        # Extract evidence refs from deterministic entities too
        for e in entities:
            for ref in e.get("evidence_refs", []):
                evidence_refs.add(ref)

        repo_context = app_context.repository_data or {}
        
        ctx = GenerationContext(
            requirement=requirement,
            pages=pages,
            controls=controls,
            forms=forms,
            apis=apis,
            flows=flows,
            modules=modules,
            repository_context=repo_context,
            retrieved_documents=retrieved_documents,
            evidence_refs=list(evidence_refs)
        )
        return ctx.to_dict()
