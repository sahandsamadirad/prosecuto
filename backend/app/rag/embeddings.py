"""Embedding selection for the RAG layer — LangChain ``Embeddings`` objects.

ARCHITECTURE.md pins the production embedder to NVIDIA NIM
(`nvidia/nv-embedqa-e5-v5`) via ``langchain-nvidia-ai-endpoints``, which needs
``NVIDIA_API_KEY`` and network. Per IMPLEMENTATION_PLAN.md's "mock first,
integrate second" rule we fall back to a fully-local MiniLM embedder (wrapped
as a LangChain ``Embeddings`` subclass) when no key is configured, so the index
and retriever can be built and tested offline.

Everything downstream (indexer, retriever) consumes a standard LangChain
``Embeddings`` instance — always obtain it through :func:`get_embeddings` so the
same backend is used at index time and query time.
"""

from __future__ import annotations

import structlog
from langchain_core.embeddings import Embeddings

from app.config import settings

log = structlog.get_logger(__name__)


class LocalMiniLMEmbeddings(Embeddings):
    """Offline LangChain ``Embeddings`` backed by ChromaDB's bundled MiniLM.

    Real semantic embeddings, no API key, no network after the one-time model
    download. Lets us validate the pipeline end to end without NIM access.
    """

    name = "local:all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions

        self._ef = embedding_functions.DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._ef(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, self._ef([text])[0]))


def get_embeddings(prefer: str | None = None) -> Embeddings:
    """Return the LangChain ``Embeddings`` backend for this process.

    Args:
        prefer: ``"nvidia"`` or ``"local"`` to force a backend. ``None`` =
            auto: NVIDIA when an API key is set, else the local fallback.
    """
    want_nvidia = prefer == "nvidia" or (
        prefer is None and bool(settings.nvidia_api_key)
    )

    if want_nvidia:
        try:
            from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

            emb = NVIDIAEmbeddings(
                model=settings.nim_embed_model, api_key=settings.nvidia_api_key
            )
            log.info("embedder.selected", provider=f"nvidia:{settings.nim_embed_model}")
            return emb
        except Exception as exc:  # noqa: BLE001 — degrade gracefully, never crash
            if prefer == "nvidia":
                raise
            log.warning("embedder.nvidia_unavailable", error=str(exc))

    emb = LocalMiniLMEmbeddings()
    log.info("embedder.selected", provider=emb.name)
    return emb
