from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from agentqe.knowledge.schemas import ApplicationKnowledgeModel
from .schemas import RAGDocument, RetrievalResult


class IRAGDocumentBuilder(ABC):
    @abstractmethod
    def build_documents(self, model: ApplicationKnowledgeModel) -> List[RAGDocument]:
        """Convert a deterministic knowledge model into RAG documents."""
        pass


class IRAGIndex(ABC):
    @abstractmethod
    def build(self, documents: List[RAGDocument]) -> None:
        """Build the vector index from documents."""
        pass
        
    @abstractmethod
    def load(self) -> None:
        """Load an existing vector index from storage."""
        pass

    @abstractmethod
    def as_retriever(self) -> "IRetriever":
        """Return a retriever for this index."""
        pass


class IRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Retrieve relevant context for a given query."""
        pass


class IRAGService(ABC):
    @abstractmethod
    def build_index(self, model: ApplicationKnowledgeModel) -> Dict[str, Any]:
        """Build or rebuild the index from the given knowledge model."""
        pass

    @abstractmethod
    def query(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Query the index and return retrieval results."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return current status of the RAG index."""
        pass
