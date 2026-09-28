from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class RAGDocument:
    """A semantic document representation of a KnowledgeModel entity, ready for LlamaIndex."""
    document_id: str
    document_type: str
    entity_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    source: str = "knowledge_model"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "entity_id": self.entity_id,
            "text": self.text,
            "metadata": self.metadata,
            "evidence_refs": self.evidence_refs,
            "source": self.source,
        }

@dataclass
class RetrievalResult:
    """A single retrieved result from the RAG layer."""
    document_id: str
    entity_id: str
    document_type: str
    score: Optional[float]
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "entity_id": self.entity_id,
            "document_type": self.document_type,
            "score": self.score,
            "text": self.text,
            "metadata": self.metadata,
            "evidence_refs": self.evidence_refs,
        }
