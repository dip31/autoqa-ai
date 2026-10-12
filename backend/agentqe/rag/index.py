import os
from typing import List, Optional
import logging

from llama_index.core import Document, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.schema import TextNode
from llama_index.core.retrievers import VectorIndexRetriever

from .schemas import RAGDocument, RetrievalResult
from .interfaces import IRAGIndex, IRetriever
from .config import (
    LOG_PREFIX,
    RAGEmbeddingConfig,
    build_embed_model,
    resolve_embedding_config,
)

logger = logging.getLogger(__name__)

class LlamaIndexRetriever(IRetriever):
    def __init__(self, index: VectorStoreIndex, embed_model=None):
        # Pass the same local embed_model used to build the index so the query
        # side embeds with the identical model. Without this, the retriever
        # would resolve Settings.embed_model (OpenAI by default) for the query
        # embedding and fail / mismatch dimensions.
        self._retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=5,
            embed_model=embed_model,
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
    def __init__(self, persist_dir: str = ".rag_storage", embed_config: Optional[RAGEmbeddingConfig] = None):
        self.persist_dir = persist_dir
        self._index: Optional[VectorStoreIndex] = None

        # Resolve the embedding configuration once and build the local model
        # lazily on first use. The model itself (torch / sentence-transformers)
        # is only imported when build()/load() actually needs it, so simply
        # constructing a LocalRAGIndex is cheap and import-safe.
        self.embed_config = embed_config or resolve_embedding_config()
        self._embed_model = None

    def _get_embed_model(self):
        """Build (once) and return the local embedding model."""
        if self._embed_model is None:
            self._embed_model = build_embed_model(self.embed_config)
            logger.info(
                "%s Embedding dimension (expected): %s",
                LOG_PREFIX, self.embed_config.dimension,
            )
        return self._embed_model

    def build(self, documents: List[RAGDocument]) -> None:
        embed_model = self._get_embed_model()

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

        logger.info("%s Building local vector index...", LOG_PREFIX)
        logger.info("%s Documents: %s", LOG_PREFIX, len(nodes))

        # Pass embed_model EXPLICITLY. This is the fix: without it,
        # VectorStoreIndex resolves Settings.embed_model, which defaults to
        # OpenAIEmbedding and fails when OPENAI_API_KEY is absent.
        self._index = VectorStoreIndex(nodes, embed_model=embed_model)

        # Ensure directory exists and persist
        os.makedirs(self.persist_dir, exist_ok=True)
        self._index.storage_context.persist(persist_dir=self.persist_dir)

        logger.info("%s Local vector index built successfully", LOG_PREFIX)

    def load(self) -> None:
        if not os.path.exists(self.persist_dir):
            raise FileNotFoundError(f"Storage directory {self.persist_dir} does not exist.")

        embed_model = self._get_embed_model()
        storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
        # Pass embed_model so re-loading an index never touches OpenAI either.
        self._index = load_index_from_storage(storage_context, embed_model=embed_model)

    def as_retriever(self) -> IRetriever:
        if not self._index:
            try:
                self.load()
            except FileNotFoundError:
                raise ValueError("Index has not been built and no persistent storage found.")
        return LlamaIndexRetriever(self._index, embed_model=self._get_embed_model())
