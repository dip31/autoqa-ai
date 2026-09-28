import os
from typing import List, Optional
import logging

from llama_index.core import Document, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.schema import TextNode
from llama_index.core.retrievers import VectorIndexRetriever

from .schemas import RAGDocument, RetrievalResult
from .interfaces import IRAGIndex, IRetriever

logger = logging.getLogger(__name__)

class LlamaIndexRetriever(IRetriever):
    def __init__(self, index: VectorStoreIndex):
        self._retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=5,
        )

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        self._retriever._similarity_top_k = top_k
        nodes = self._retriever.retrieve(query)
        
        results = []
        for node in nodes:
            metadata = node.metadata or {}
            
            # The evidence_refs might have been stored as a string or list
            evidence_refs = metadata.get("evidence_refs", [])
            if isinstance(evidence_refs, str):
                try:
                    import json
                    evidence_refs = json.loads(evidence_refs)
                except:
                    evidence_refs = []
                    
            results.append(RetrievalResult(
                document_id=metadata.get("document_id", ""),
                entity_id=metadata.get("entity_id", ""),
                document_type=metadata.get("document_type", ""),
                score=node.score,
                text=node.text,
                metadata=metadata,
                evidence_refs=evidence_refs if isinstance(evidence_refs, list) else []
            ))
            
        return results

class LocalRAGIndex(IRAGIndex):
    def __init__(self, persist_dir: str = ".rag_storage"):
        self.persist_dir = persist_dir
        self._index: Optional[VectorStoreIndex] = None
        
    def build(self, documents: List[RAGDocument]) -> None:
        nodes = []
        import json
        for doc in documents:
            metadata = doc.metadata.copy()
            metadata["document_id"] = doc.document_id
            metadata["entity_id"] = doc.entity_id
            metadata["document_type"] = doc.document_type
            
            # Store evidence refs as string to avoid schema complex type issues
            if doc.evidence_refs:
                metadata["evidence_refs"] = json.dumps(doc.evidence_refs)
                
            node = TextNode(
                id_=doc.document_id,
                text=doc.text,
                metadata=metadata
            )
            nodes.append(node)
            
        self._index = VectorStoreIndex(nodes)
        
        # Ensure directory exists and persist
        os.makedirs(self.persist_dir, exist_ok=True)
        self._index.storage_context.persist(persist_dir=self.persist_dir)
        
    def load(self) -> None:
        if not os.path.exists(self.persist_dir):
            raise FileNotFoundError(f"Storage directory {self.persist_dir} does not exist.")
            
        storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
        self._index = load_index_from_storage(storage_context)

    def as_retriever(self) -> IRetriever:
        if not self._index:
            try:
                self.load()
            except FileNotFoundError:
                raise ValueError("Index has not been built and no persistent storage found.")
        return LlamaIndexRetriever(self._index)
