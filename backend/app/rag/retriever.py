"""ProsecutoRetriever — Self-RAG retrieve + rerank + relevance gate.

Implements ARCHITECTURE.md section 8. The retrieval half of the Self-RAG flow:

    Chroma similarity (top-k)
      → LocalCrossEncoderReranker / IdentityReranker fallback (top-n)
      → Relevance critic (drop irrelevant passages)
      → return passages, OR trigger Tavily fallback when nothing survives.

All reranking is local (BAAI/bge-reranker-v2-m3 via sentence-transformers).
No cloud reranking calls.
"""

from __future__ import annotations

from typing import Protocol

import asyncio
import structlog
from langchain_core.documents import Document

from app.config import settings
from app.rag.critic import Critics, get_critics
from app.rag.results import Passage, RetrievalResult
from app.rag.tavily_fallback import TavilyFallback

log = structlog.get_logger(__name__)


class Reranker(Protocol):
    def compress_documents(
        self, documents: list[Document], query: str
    ) -> list[Document]: ...


class IdentityReranker:
    """Offline fallback: preserves order, no reranking."""

    name = "identity"

    def compress_documents(self, documents: list[Document], query: str) -> list[Document]:
        return list(documents)


class LocalCrossEncoderReranker:
    """Local cross-encoder reranker using sentence-transformers.

    Scores each (query, document) pair jointly. Runs on GPU when available.
    Model: BAAI/bge-reranker-v2-m3 (~560 MB, multilingual, strong on legal text).
    """

    name = "local:BAAI/bge-reranker-v2-m3"

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", top_n: int = 4) -> None:
        import torch
        from sentence_transformers import CrossEncoder

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = CrossEncoder(model_name, device=device)
        self._top_n = top_n
        log.info("reranker.loaded", model=model_name, device=device)

    def compress_documents(self, documents: list[Document], query: str) -> list[Document]:
        if not documents:
            return []
        pairs = [(query, doc.page_content) for doc in documents]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(scores, documents), key=lambda x: x[0], reverse=True)
        reranked = []
        for score, doc in ranked[: self._top_n]:
            doc.metadata["relevance_score"] = float(score)
            reranked.append(doc)
        return reranked


def get_reranker(top_n: int = 4) -> Reranker:
    """Return the local cross-encoder reranker, falling back to identity."""
    try:
        rr = LocalCrossEncoderReranker(top_n=top_n)
        log.info("reranker.selected", provider=rr.name)
        return rr
    except Exception as exc:  # noqa: BLE001
        log.warning("reranker.local_unavailable", error=str(exc))

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
        scored = self.vectorstore.similarity_search_with_score(query, k=k, filter=filters)
        if not scored:
            return self._tavily_result(query)

        docs = [d for d, _ in scored]
        sim_scores = {id(d): s for d, s in scored}
        reranked = self.reranker.compress_documents(documents=docs, query=query)[:n]

        kept: list[Passage] = []
        for doc in reranked:
            if grade:
                grade_res = self.critics.grade_relevance(query, doc.page_content)
                if not grade_res.relevant:
                    continue
            score = doc.metadata.get("relevance_score", sim_scores.get(id(doc)))
            kept.append(Passage.from_document(doc, score=score))

        if not kept:
            return self._tavily_result(query)

        return RetrievalResult(query=query, passages=kept, source="rag", scores=[p.score or 0.0 for p in kept])

    async def aretrieve(
        self,
        query: str,
        k: int = 8,
        n: int = 4,
        filters: dict | None = None,
        grade: bool = True,
    ) -> RetrievalResult:
        scored = await asyncio.to_thread(
            self.vectorstore.similarity_search_with_score, query, k=k, filter=filters
        )
        if not scored:
            log.info("retriever.empty_chroma", query=query)
            return await self.atavily_result(query)

        docs = [d for d, _ in scored]
        sim_scores = {id(d): s for d, s in scored}

        reranked = (await asyncio.to_thread(self.reranker.compress_documents, documents=docs, query=query))[:n]

        if not grade:
            kept = [Passage.from_document(doc, score=doc.metadata.get("relevance_score", sim_scores.get(id(doc)))) for doc in reranked]
        else:
            grades = await asyncio.gather(*[self.critics.agrade_relevance(query, d.page_content) for d in reranked])
            kept = []
            for doc, g in zip(reranked, grades):
                if g.relevant:
                    score = doc.metadata.get("relevance_score", sim_scores.get(id(doc)))
                    kept.append(Passage.from_document(doc, score=score))

        if not kept:
            log.info("retriever.no_relevant", query=query)
            return await self.atavily_result(query)

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

    async def atavily_result(self, query: str) -> RetrievalResult:
        passages = await asyncio.to_thread(self.tavily.search, query)
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
    if vectorstore is None:
        from app.rag.indexer import get_vectorstore
        vectorstore = get_vectorstore()
    return ProsecutoRetriever(
        vectorstore=vectorstore,
        reranker=reranker or get_reranker(top_n=top_n),
        critics=critics or get_critics(),
        tavily=tavily or TavilyFallback(),
    )
