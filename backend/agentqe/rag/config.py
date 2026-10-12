"""
Phase 2 — AgentQE RAG embedding configuration.

Single source of truth for *which* embedding model the RAG layer uses and *how*
it is constructed. Nothing else in ``agentqe.rag`` should name an embedding
model directly — they call :func:`resolve_embedding_config` /
:func:`build_embed_model` instead.

Why this file exists
--------------------
LlamaIndex, when handed no ``embed_model``, lazily resolves
``Settings.embed_model`` which defaults to ``OpenAIEmbedding`` and then validates
``OPENAI_API_KEY``. With no key that raises::

    Could not load OpenAI embedding model. No API key found for OpenAI.

AgentQE runs fully locally and must never depend on OpenAI for embeddings, so we
configure a local Sentence-Transformers model explicitly and pass it into every
index build/load path.

Default model
-------------
``sentence-transformers/all-MiniLM-L6-v2`` — 384-dimensional, small, fast, CPU
friendly, and cached locally after the first download. This default requires no
environment variables.

Environment overrides (all optional)
------------------------------------
``AGENTQE_RAG_EMBEDDING_MODEL``
    Override the model name (still resolved through the local HuggingFace
    integration). Not required for normal local development.
``AGENTQE_RAG_EMBEDDING_PROVIDER``
    ``huggingface`` (default) or ``mock``. ``mock`` selects a deterministic,
    dependency-free embedding used by unit tests so they never download a model
    or touch the network. Production/normal runs use ``huggingface``.
``AGENTQE_RAG_EMBEDDING_DEVICE``
    Optional device hint passed through to the HuggingFace integration
    (e.g. ``cpu`` or ``cuda``). Left unset, the library chooses.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — the canonical local embedding choice for AgentQE.
# ---------------------------------------------------------------------------

#: Provider identifiers we support. ``huggingface`` = local Sentence-Transformers
#: via LlamaIndex; ``mock`` = deterministic offline embedding for tests only.
PROVIDER_HUGGINGFACE = "huggingface"
PROVIDER_MOCK = "mock"

#: The required local model. Do not swap for OpenAI/BGE/Cohere/etc.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

#: Known output dimension of all-MiniLM-L6-v2. Used only for logging and for the
#: mock provider — never passed to the real integration, which determines the
#: dimension itself.
DEFAULT_EMBEDDING_DIMENSION = 384

#: Environment variable names (documented in the module docstring).
ENV_MODEL = "AGENTQE_RAG_EMBEDDING_MODEL"
ENV_PROVIDER = "AGENTQE_RAG_EMBEDDING_PROVIDER"
ENV_DEVICE = "AGENTQE_RAG_EMBEDDING_DEVICE"

#: Log-line prefix so the embedding configuration is greppable in server logs.
LOG_PREFIX = "[AgentQE RAG]"


@dataclass(frozen=True)
class RAGEmbeddingConfig:
    """
    Resolved embedding configuration.

    Immutable so it can be safely shared. Construct it through
    :func:`resolve_embedding_config` rather than directly, so environment
    overrides are applied consistently.
    """

    provider: str = PROVIDER_HUGGINGFACE
    model_name: str = DEFAULT_EMBEDDING_MODEL
    dimension: int = DEFAULT_EMBEDDING_DIMENSION
    device: Optional[str] = None

    @property
    def is_local(self) -> bool:
        """True for every provider we support — none call a cloud service."""
        return self.provider in (PROVIDER_HUGGINGFACE, PROVIDER_MOCK)

    def describe(self) -> str:
        return f"provider={self.provider} model={self.model_name} dim={self.dimension}"


def resolve_embedding_config() -> RAGEmbeddingConfig:
    """
    Build the effective :class:`RAGEmbeddingConfig` from defaults + environment.

    The default (no env vars set) is the local all-MiniLM-L6-v2 model through the
    HuggingFace integration and requires no ``OPENAI_API_KEY``.
    """
    provider = (os.environ.get(ENV_PROVIDER) or PROVIDER_HUGGINGFACE).strip().lower()
    if provider not in (PROVIDER_HUGGINGFACE, PROVIDER_MOCK):
        logger.warning(
            "%s Unknown embedding provider %r; falling back to %r.",
            LOG_PREFIX, provider, PROVIDER_HUGGINGFACE,
        )
        provider = PROVIDER_HUGGINGFACE

    model_name = (os.environ.get(ENV_MODEL) or DEFAULT_EMBEDDING_MODEL).strip()
    if not model_name:
        model_name = DEFAULT_EMBEDDING_MODEL

    device = (os.environ.get(ENV_DEVICE) or "").strip() or None

    return RAGEmbeddingConfig(
        provider=provider,
        model_name=model_name,
        dimension=DEFAULT_EMBEDDING_DIMENSION,
        device=device,
    )


def build_embed_model(config: Optional[RAGEmbeddingConfig] = None) -> Any:
    """
    Construct the concrete LlamaIndex embedding object for ``config``.

    * ``huggingface`` → ``HuggingFaceEmbedding`` from
      ``llama-index-embeddings-huggingface`` (local Sentence-Transformers).
      Imported lazily so importing this module never drags in torch.
    * ``mock`` → ``MockEmbedding`` from ``llama-index-core`` (offline, no
      download); used by unit tests only.

    Raises a clear, actionable error if the HuggingFace integration is not
    installed — we deliberately do **not** silently fall back to OpenAI.
    """
    config = config or resolve_embedding_config()

    if config.provider == PROVIDER_MOCK:
        # Deterministic, dependency-free — safe for unit tests and CI.
        from llama_index.core.embeddings import MockEmbedding

        logger.info(
            "%s Embedding provider: %s (offline test embedding)",
            LOG_PREFIX, PROVIDER_MOCK,
        )
        return MockEmbedding(embed_dim=config.dimension)

    # provider == huggingface (the normal, local path)
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "AgentQE RAG is configured to use the local embedding model "
            f"'{config.model_name}' via the HuggingFace integration, but the "
            "package 'llama-index-embeddings-huggingface' (and its dependency "
            "'sentence-transformers') is not installed.\n"
            "Install it into the backend environment:\n"
            "    pip install llama-index-embeddings-huggingface sentence-transformers\n"
            "AgentQE does NOT fall back to OpenAI embeddings, so this is a hard "
            "requirement for local RAG."
        ) from exc

    logger.info("%s Embedding provider: %s", LOG_PREFIX, PROVIDER_HUGGINGFACE)
    logger.info("%s Embedding model: %s", LOG_PREFIX, config.model_name)

    kwargs = {"model_name": config.model_name}
    if config.device:
        kwargs["device"] = config.device
    # Do not pass a dimension: the model reports its own (384 for MiniLM-L6-v2).
    return HuggingFaceEmbedding(**kwargs)


__all__ = [
    "PROVIDER_HUGGINGFACE",
    "PROVIDER_MOCK",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSION",
    "ENV_MODEL",
    "ENV_PROVIDER",
    "ENV_DEVICE",
    "LOG_PREFIX",
    "RAGEmbeddingConfig",
    "resolve_embedding_config",
    "build_embed_model",
]
