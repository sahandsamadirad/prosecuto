"""Embedding selection for the RAG layer — fully local, no cloud calls.

Primary: sentence-transformers with BAAI/bge-large-en-v1.5 (1024-dim),
running on GPU when available via the shared HuggingFace cache volume.
Fallback: ChromaDB's bundled MiniLM if sentence-transformers is not installed.

Always obtain the embedder through :func:`get_embeddings` so the same backend
is used at index time and query time.
"""

from __future__ import annotations

import structlog
from langchain_core.embeddings import Embeddings

from app.config import settings

log = structlog.get_logger(__name__)


class LocalSentenceTransformerEmbeddings(Embeddings):
    """LangChain Embeddings backed by a local sentence-transformers model.

    Runs on GPU when torch detects CUDA, otherwise CPU. The model is downloaded
    once to the HuggingFace cache volume and reused across container restarts.
    """

    def __init__(self, model_name: str) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = SentenceTransformer(model_name, device=device)
        self.name = f"local:{model_name}"
        log.info("embedder.loaded", model=model_name, device=device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(
            [text], normalize_embeddings=True, show_progress_bar=False
        )[0].tolist()


class LocalMiniLMEmbeddings(Embeddings):
    """Last-resort fallback using ChromaDB's bundled MiniLM (384-dim).

    No extra dependencies, but lower retrieval quality than bge-large.
    Only used when sentence-transformers is not installed.
    """

    name = "local:all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions
        self._ef = embedding_functions.DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._ef(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, self._ef([text])[0]))


def get_embeddings() -> Embeddings:
    """Return the local embedding backend for this process.

    Tries sentence-transformers with the configured model first, falls back
    to MiniLM if the package is unavailable.
    """
    try:
        emb = LocalSentenceTransformerEmbeddings(settings.local_embed_model)
        log.info("embedder.selected", provider=emb.name)
        return emb
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "embedder.sentence_transformers_unavailable",
            error=str(exc),
            fallback="MiniLM-L6-v2",
        )

    emb = LocalMiniLMEmbeddings()
    log.info("embedder.selected", provider=emb.name)
    return emb
