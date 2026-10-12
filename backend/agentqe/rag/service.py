import logging
import time
from typing import Dict, Any, List

from agentqe.knowledge.schemas import ApplicationKnowledgeModel
from .schemas import RetrievalResult
from .interfaces import IRAGService
from .document_builder import DeterministicRAGDocumentBuilder
from .index import LocalRAGIndex
from .config import LOG_PREFIX, resolve_embedding_config

logger = logging.getLogger(__name__)

class RAGService(IRAGService):
    def __init__(self, persist_dir: str = ".rag_storage"):
        self.persist_dir = persist_dir
        self.builder = DeterministicRAGDocumentBuilder()

        # Resolve the embedding configuration up front and log it, so the chosen
        # local model is visible in server logs before any indexing happens.
        self.embed_config = resolve_embedding_config()
        logger.info("%s Embedding provider: %s", LOG_PREFIX, self.embed_config.provider)
        logger.info("%s Embedding model: %s", LOG_PREFIX, self.embed_config.model_name)

        self.index = LocalRAGIndex(persist_dir=persist_dir, embed_config=self.embed_config)

        self.last_build_time = None
        self.document_count = 0
        self.is_ready = False

        # Try to load existing index. This is best-effort: a failure here (e.g.
        # no prior index, or the embed model not yet downloaded) must not raise —
        # build_index will construct it on demand.
        try:
            self.index.load()
            self.is_ready = True
            logger.info("%s Loaded existing local vector index", LOG_PREFIX)
        except Exception:
            pass

    def build_index(self, model: ApplicationKnowledgeModel) -> Dict[str, Any]:
        """Build or rebuild the index from the given knowledge model."""
        start_time = time.time()
        
        try:
            # 1. Build documents
            docs = self.builder.build_documents(model)
            self.document_count = len(docs)
            
            # 2. Build index
            self.index.build(docs)
            
            self.is_ready = True
            self.last_build_time = time.time()
            duration_ms = round((time.time() - start_time) * 1000.2, 2)
            
            logger.info(f"Built RAG index with {self.document_count} documents in {duration_ms}ms")
            
            return {
                "status": "success",
                "document_count": self.document_count,
                "duration_ms": duration_ms
            }
        except Exception as e:
            logger.error(f"Failed to build RAG index: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    def query(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Query the index and return retrieval results."""
        if not self.is_ready:
            raise ValueError("RAG index is not ready. Call build_index first.")
            
        retriever = self.index.as_retriever()
        return retriever.retrieve(query, top_k=top_k)

    def get_status(self) -> Dict[str, Any]:
        """Return current status of the RAG index."""
        return {
            "status": "ready" if self.is_ready else "not_ready",
            "document_count": self.document_count,
            "last_build_time": self.last_build_time
        }
