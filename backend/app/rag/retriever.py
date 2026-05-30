"""ProsecutoRetriever — Self-RAG retrieve + rerank + relevance gate.

Implements ARCHITECTURE.md section 8. The retrieval half of the Self-RAG flow:

    Chroma similarity (top-k)
      → NVIDIARerank (top-n)
      → Relevance critic (drop irrelevant passages)
      → return passages, OR trigger Tavily fallback when nothing survives.

Built entirely on LangChain primitives (``langchain_chroma.Chroma`` vectorstore,
``NVIDIARerank`` compressor). Every external dependency is injectable so the
retriever can be unit-tested offline.
"""

from __future__ import annotations

from typing import Protocol

import structlog
from langchain_core.documents import Document

from app.config import settings
from app.rag.critic import Critics, get_critics
from app.rag.results import Passage, RetrievalResult
from app.rag.tavily_fallback import TavilyFallback

log = structlog.get_logger(__name__)


class Reranker(Protocol):
    """Minimal reranker interface (``NVIDIARerank`` satisfies this)."""

    def compress_documents(
        self, documents: list[Document], query: str
    ) -> list[Document]: ...


class IdentityReranker:
    """Offline fallback: preserves order, no reranking. Caller slices to top-n."""

    name = "identity"

    def compress_documents(self, documents: list[Document], query: str) -> list[Document]:
        return list(documents)


def get_reranker(prefer: str | None = None, top_n: int = 4) -> Reranker:
    """NVIDIARerank when a key is configured, else an identity passthrough."""
    want_nvidia = prefer == "nvidia" or (prefer is None and bool(settings.nvidia_api_key))
    if want_nvidia:
        try:
            from langchain_nvidia_ai_endpoints import NVIDIARerank

            rr = NVIDIARerank(
                model=settings.nim_rerank_model,
                api_key=settings.nvidia_api_key,
                top_n=top_n,
            )
            log.info("reranker.selected", provider=f"nvidia:{settings.nim_rerank_model}")
            return rr
        except Exception as exc:  # noqa: BLE001
            if prefer == "nvidia":
                raise
            log.warning("reranker.nvidia_unavailable", error=str(exc))
    log.info("reranker.selected", provider="identity")
    return IdentityReranker()


class ProsecutoRetriever:
    """Retrieve + rerank + relevance-gate, with Tavily fallback."""

    def __init__(
        self,
        vectorstore,
        reranker: Reranker,
        critics: Critics,
        tavily: TavilyFallback,
    ) -> None:
        self.vectorstore = vectorstore
        self.reranker = reranker
        self.critics = critics
        self.tavily = tavily

    def retrieve(
        self,
        query: str,
        k: int = 8,
        n: int = 4,
        filters: dict | None = None,
        grade: bool = True,
    ) -> RetrievalResult:
        """Return reranked, relevance-graded passages for ``query``.

        Args:
            k: initial Chroma retrieval depth.
            n: passages kept after reranking.
            filters: optional Chroma metadata ``where`` clause.
            grade: run the relevance critic (set False for a raw retrieve).
        """
        # 1. Chroma similarity search, top-k.
        scored = self.vectorstore.similarity_search_with_score(query, k=k, filter=filters)
        if not scored:
            log.info("retriever.empty_chroma", query=query)
            return self._tavily_result(query)

        docs = [d for d, _ in scored]
        sim_scores = {id(d): s for d, s in scored}

        # 2. Rerank to top-n.
        reranked = self.reranker.compress_documents(documents=docs, query=query)[:n]

        # 3. Relevance critic — drop irrelevant passages.
        kept: list[Passage] = []
        for doc in reranked:
            if grade:
                grade_res = self.critics.grade_relevance(query, doc.page_content)
                if not grade_res.relevant:
                    continue
            score = doc.metadata.get("relevance_score", sim_scores.get(id(doc)))
            kept.append(Passage.from_document(doc, score=score))

        # 4. Nothing relevant → Tavily fallback.
        if not kept:
            log.info("retriever.no_relevant", query=query)
            return self._tavily_result(query)

        log.info("retriever.rag", query=query, kept=len(kept))
        return RetrievalResult(
            query=query,
            passages=kept,
            scores=[p.score or 0.0 for p in kept],
            source="rag",
        )

    def _tavily_result(self, query: str) -> RetrievalResult:
        passages = self.tavily.search(query)
        return RetrievalResult(
            query=query,
            passages=passages,
            scores=[p.score or 0.0 for p in passages],
            source="tavily" if passages else "none",
        )


def get_retriever(
    vectorstore=None,
    reranker: Reranker | None = None,
    critics: Critics | None = None,
    tavily: TavilyFallback | None = None,
    top_n: int = 4,
) -> ProsecutoRetriever:
    """Build a retriever wired to the default NVIDIA-backed components.

    A fresh ``TavilyFallback`` is created per call so its cache is session-scoped
    — construct one retriever per session.
    """
    if vectorstore is None:
        from app.rag.indexer import get_vectorstore

        vectorstore = get_vectorstore()
    return ProsecutoRetriever(
        vectorstore=vectorstore,
        reranker=reranker or get_reranker(top_n=top_n),
        critics=critics or get_critics(),
        tavily=tavily or TavilyFallback(),
    )
