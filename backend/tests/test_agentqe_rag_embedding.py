"""
Phase 2 — AgentQE RAG local-embedding configuration tests.

These verify the fix that stops LlamaIndex from falling back to OpenAI
embeddings and makes it use the local Sentence-Transformers model
``sentence-transformers/all-MiniLM-L6-v2`` instead.

Design notes
------------
* The pure-config tests have no third-party dependency and run everywhere.
* The tests that actually build/query an index use the offline ``mock``
  embedding provider (``MockEmbedding`` from ``llama-index-core``) via the
  ``AGENTQE_RAG_EMBEDDING_PROVIDER=mock`` override, so they never download a
  model or touch the network. They are skipped automatically if ``llama_index``
  cannot be imported in the current environment.
* A single, opt-in real-model test (``test_real_all_minilm_embedding``) runs the
  actual all-MiniLM-L6-v2 model. It is skipped unless
  ``AGENTQE_RAG_RUN_REAL_EMBEDDING=1`` so normal CI stays offline.
"""

import os
import importlib

import pytest

from agentqe.rag import config as rag_config
from agentqe.rag.config import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    PROVIDER_HUGGINGFACE,
    PROVIDER_MOCK,
    RAGEmbeddingConfig,
    resolve_embedding_config,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_ENV_KEYS = (
    rag_config.ENV_MODEL,
    rag_config.ENV_PROVIDER,
    rag_config.ENV_DEVICE,
)


@pytest.fixture(autouse=True)
def _clean_rag_env(monkeypatch):
    """Ensure each test starts with no RAG embedding env overrides."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def _has_llama_index() -> bool:
    return importlib.util.find_spec("llama_index") is not None


llama_index_required = pytest.mark.skipif(
    not _has_llama_index(),
    reason="llama_index is not importable in this environment",
)


def _sample_knowledge_model():
    """A tiny deterministic ApplicationKnowledgeModel with a login page + api."""
    from agentqe.knowledge.schemas import (
        ApplicationKnowledgeModel,
        KnowledgeEntity,
        KnowledgeRelationship,
    )

    entities = [
        KnowledgeEntity(
            id="page:login",
            entity_type="page",
            name="Login",
            display_name="Login",
            canonical_name="login",
            properties={"url": "https://app.example.com/login", "page_type": "login"},
            evidence_refs=["dom:page_001", "visual:page_001"],
            status="observed",
        ),
        KnowledgeEntity(
            id="control:sign_in",
            entity_type="control",
            name="Sign In",
            display_name="Sign In",
            canonical_name="sign_in",
            properties={"type": "button", "interactable": True},
            evidence_refs=["dom:page_001:element_007"],
            status="observed",
        ),
        KnowledgeEntity(
            id="api:post:/api/auth/login",
            entity_type="api_endpoint",
            name="POST /api/auth/login",
            display_name="POST /api/auth/login",
            canonical_name="post_api_auth_login",
            properties={"method": "POST", "path": "/api/auth/login"},
            evidence_refs=["network:req_003"],
            status="observed",
        ),
    ]
    relationships = [
        KnowledgeRelationship(
            id="rel:page_login:has_control:control_sign_in",
            source_id="page:login",
            relationship="has_control",
            target_id="control:sign_in",
            status="observed",
        ),
    ]
    return ApplicationKnowledgeModel(entities=entities, relationships=relationships)


# ---------------------------------------------------------------------------
# Pure configuration tests (no third-party deps)
# ---------------------------------------------------------------------------

def test_embedding_provider_is_local():
    cfg = resolve_embedding_config()
    assert cfg.provider == PROVIDER_HUGGINGFACE
    assert cfg.is_local is True


def test_embedding_model_is_all_minilm_l6_v2():
    cfg = resolve_embedding_config()
    assert cfg.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.model_name == DEFAULT_EMBEDDING_MODEL


def test_embedding_dimension():
    cfg = resolve_embedding_config()
    assert cfg.dimension == 384
    assert cfg.dimension == DEFAULT_EMBEDDING_DIMENSION


def test_openai_embedding_is_not_selected():
    # Default provider/model must not reference OpenAI at all.
    cfg = resolve_embedding_config()
    assert "openai" not in cfg.provider.lower()
    assert "openai" not in cfg.model_name.lower()


def test_openai_provider_override_falls_back_to_local(monkeypatch):
    # Even an explicit attempt to select openai is refused — RAG stays local.
    monkeypatch.setenv(rag_config.ENV_PROVIDER, "openai")
    cfg = resolve_embedding_config()
    assert cfg.provider == PROVIDER_HUGGINGFACE


def test_env_override_model(monkeypatch):
    monkeypatch.setenv(rag_config.ENV_MODEL, "sentence-transformers/all-MiniLM-L6-v2")
    cfg = resolve_embedding_config()
    assert cfg.model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_env_override_provider_mock(monkeypatch):
    monkeypatch.setenv(rag_config.ENV_PROVIDER, "mock")
    cfg = resolve_embedding_config()
    assert cfg.provider == PROVIDER_MOCK
    assert cfg.is_local is True


def test_openai_key_not_required(monkeypatch):
    # Removing OPENAI_API_KEY must not affect configuration resolution at all.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = resolve_embedding_config()
    assert cfg.provider == PROVIDER_HUGGINGFACE
    assert cfg.model_name == DEFAULT_EMBEDDING_MODEL


def test_build_embed_model_never_silently_uses_openai(monkeypatch):
    """
    With the huggingface provider selected, build_embed_model must either return
    a HuggingFace embedding (if installed) or raise an actionable ImportError —
    but must never return an OpenAI embedding.
    """
    monkeypatch.setenv(rag_config.ENV_PROVIDER, PROVIDER_HUGGINGFACE)
    try:
        model = rag_config.build_embed_model()
    except ImportError as exc:
        assert "llama-index-embeddings-huggingface" in str(exc)
        assert "OpenAI" in str(exc)  # message explicitly says we don't fall back
        return
    # If it did build, it must be the HuggingFace class, not OpenAI.
    assert "OpenAI" not in type(model).__name__


# ---------------------------------------------------------------------------
# Index build/query tests using the offline mock embedding
# ---------------------------------------------------------------------------

@llama_index_required
def test_local_rag_index_build(monkeypatch, tmp_path):
    monkeypatch.setenv(rag_config.ENV_PROVIDER, "mock")
    from agentqe.rag.index import LocalRAGIndex
    from agentqe.rag.document_builder import DeterministicRAGDocumentBuilder

    docs = DeterministicRAGDocumentBuilder().build_documents(_sample_knowledge_model())
    assert len(docs) == 3

    index = LocalRAGIndex(persist_dir=str(tmp_path / "rag"), embed_config=resolve_embedding_config())
    index.build(docs)

    # The chosen embed model must be the offline mock, never OpenAI.
    assert type(index._get_embed_model()).__name__ == "MockEmbedding"
    assert os.path.isdir(str(tmp_path / "rag"))


@llama_index_required
def test_rag_documents_are_indexed(monkeypatch, tmp_path):
    monkeypatch.setenv(rag_config.ENV_PROVIDER, "mock")
    from agentqe.rag.service import RAGService

    service = RAGService(persist_dir=str(tmp_path / "rag"))
    result = service.build_index(_sample_knowledge_model())

    assert result["status"] == "success"
    assert result["document_count"] == 3
    assert service.is_ready is True

    # Retrieval returns results that map back to real knowledge entities.
    results = service.query("login page controls", top_k=3)
    assert len(results) > 0
    entity_ids = {r.entity_id for r in results}
    assert entity_ids <= {"page:login", "control:sign_in", "api:post:/api/auth/login"}


@llama_index_required
def test_service_logs_local_provider(monkeypatch, tmp_path, caplog):
    import logging
    monkeypatch.setenv(rag_config.ENV_PROVIDER, "mock")
    from agentqe.rag.service import RAGService

    with caplog.at_level(logging.INFO):
        RAGService(persist_dir=str(tmp_path / "rag"))
    text = caplog.text
    assert "[AgentQE RAG] Embedding provider:" in text
    assert "[AgentQE RAG] Embedding model: sentence-transformers/all-MiniLM-L6-v2" in text


def test_rag_failure_does_not_break_application_understanding(monkeypatch):
    """
    If the RAG service raises while building, build_index must swallow it and
    return a structured failure (the caller in the agent then keeps the
    knowledge model). We simulate the failure via a builder that raises.
    """
    from agentqe.rag.service import RAGService

    service = RAGService.__new__(RAGService)  # bypass __init__ (no llama_index needed)
    service.document_count = 0
    service.is_ready = False
    service.last_build_time = None

    class _BoomBuilder:
        def build_documents(self, model):
            raise RuntimeError("simulated embedding failure")

    class _NoIndex:
        def build(self, docs):
            raise AssertionError("should not reach index.build")

    service.builder = _BoomBuilder()
    service.index = _NoIndex()

    result = service.build_index(_sample_knowledge_model())
    assert result["status"] == "failed"
    assert "simulated embedding failure" in result["error"]
    # Crucially, no exception escaped — application understanding can continue.


# ---------------------------------------------------------------------------
# Opt-in real model test (downloads / loads all-MiniLM-L6-v2)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("AGENTQE_RAG_RUN_REAL_EMBEDDING") != "1",
    reason="set AGENTQE_RAG_RUN_REAL_EMBEDDING=1 to run the real embedding model",
)
def test_real_all_minilm_embedding():
    """Real integration: load the actual model and embed a string (dim 384)."""
    cfg = RAGEmbeddingConfig(provider=PROVIDER_HUGGINGFACE, model_name=DEFAULT_EMBEDDING_MODEL)
    model = rag_config.build_embed_model(cfg)
    vector = model.get_text_embedding("How does the login flow work?")
    assert len(vector) == 384
