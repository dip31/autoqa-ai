import json
from typing import List, Dict, Any, Set
from collections import defaultdict

from agentqe.knowledge.schemas import ApplicationKnowledgeModel, KnowledgeEntity
from agentqe.knowledge.index import KnowledgeIndex
from .interfaces import IRAGDocumentBuilder
from .schemas import RAGDocument

class DeterministicRAGDocumentBuilder(IRAGDocumentBuilder):
    def build_documents(self, model: ApplicationKnowledgeModel) -> List[RAGDocument]:
        documents: List[RAGDocument] = []
        if not model or not model.entities:
            return documents

        index = KnowledgeIndex.build(model)
        
        # Build documents for all entities, enriching them with relationship context
        for entity in model.entities:
            doc = self._build_document_for_entity(entity, index)
            if doc:
                documents.append(doc)
                
        return documents

    def _build_document_for_entity(self, entity: KnowledgeEntity, index: KnowledgeIndex) -> RAGDocument:
        # Get immediate neighbors for context
        outgoing = index.outgoing(entity.id)
        incoming = index.incoming(entity.id)
        
        # Build a rich text representation
        lines = []
        lines.append(f"TYPE: {entity.entity_type}")
        lines.append(f"NAME: {entity.name or entity.display_name or entity.id}")
        if entity.description:
            lines.append(f"DESCRIPTION: {entity.description}")
            
        # Properties
        if entity.properties:
            lines.append("PROPERTIES:")
            for k, v in entity.properties.items():
                # Serialize dict/list safely
                if isinstance(v, (dict, list)):
                    try:
                        v_str = json.dumps(v, ensure_ascii=False)
                    except:
                        v_str = str(v)
                else:
                    v_str = str(v)
                lines.append(f"  - {k}: {v_str}")
                
        # Relationships
        if outgoing or incoming:
            lines.append("RELATIONSHIPS:")
            for rel in outgoing:
                target = index.entities_by_id.get(rel.target_id)
                target_name = target.name or target.id if target else rel.target_id
                lines.append(f"  - (Outgoing) {rel.relationship} -> {target_name} ({rel.target_id})")
            for rel in incoming:
                source = index.entities_by_id.get(rel.source_id)
                source_name = source.name or source.id if source else rel.source_id
                lines.append(f"  - (Incoming) {source_name} ({rel.source_id}) -> {rel.relationship}")
                
        # Evidence refs
        if entity.evidence_refs:
            lines.append("EVIDENCE:")
            for ref in entity.evidence_refs:
                lines.append(f"  - {ref}")

        text = "\n".join(lines)
        
        # Deterministic document ID derived from entity ID
        doc_id = f"rag:{entity.id}"
        
        metadata = {
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
            "status": entity.status,
            "has_evidence": len(entity.evidence_refs) > 0
        }
        
        # Flatten properties into metadata if they are primitive
        for k, v in entity.properties.items():
            if isinstance(v, (str, int, float, bool)) and len(str(v)) < 500:
                metadata[f"prop_{k}"] = v
                
        return RAGDocument(
            document_id=doc_id,
            document_type=entity.entity_type,
            entity_id=entity.id,
            text=text,
            metadata=metadata,
            evidence_refs=list(entity.evidence_refs),
            source="knowledge_model"
        )
