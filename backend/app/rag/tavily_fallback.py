"""Tavily web-search fallback for the Self-RAG pipeline.

ARCHITECTURE.md section 6 "Tavily Fallback Rules":
* triggered when the relevance critic finds no relevant docs, or the
  answer-adequacy critic fails on the RAG path;
* ``max_results`` capped (default 5, from settings);
* instruction-guided — the Ontario jurisdiction is pinned into the query;
* results are cached **per session** — the same query within a session reuses
  results instead of re-calling the API.

One instance is created per session so the cache is naturally session-scoped.
Mirrors the reference ``search-agent`` / ``web_search`` node pattern, but kept
as a thin wrapper rather than a LangChain tool so the retriever can call it
directly.
"""

from __future__ import annotations

import time
import structlog

from app.config import settings
from app.rag.results import Passage

log = structlog.get_logger(__name__)

# Pin jurisdiction so the crawl stays on-topic (instruction-guided).
_QUERY_SUFFIX = " Ontario red light camera ticket law"


class TavilyFallback:
    """Session-scoped Tavily search wrapper with an in-memory query cache."""

    def __init__(self, client=None, max_results: int | None = None) -> None:
        self.max_results = max_results or settings.tavily_max_sources
        self._cache: dict[str, list[Passage]] = {}
        self._client = client  # injectable for tests; lazily created otherwise

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.tavily_api_key:
            return None
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=settings.tavily_api_key)
        return self._client

    def search(self, query: str) -> list[Passage]:
        """Return up to ``max_results`` passages; ``[]`` if Tavily is unavailable."""
        if query in self._cache:
            log.info("tavily.cache_hit", query=query)
            return self._cache[query]

        client = self._get_client()
        if client is None:
            log.warning("tavily.unavailable", reason="no api key / client")
            self._cache[query] = []
            return []

        guided = query if "ontario" in query.lower() else query + _QUERY_SUFFIX
        
        # Phase 11 hardening: retry with backoff.
        max_retries = 2
        resp = {}
        for attempt in range(max_retries + 1):
            try:
                resp = client.search(query=guided, max_results=self.max_results)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt < max_retries:
                    log.warning("tavily.retry", attempt=attempt + 1, error=str(exc))
                    time.sleep(1 * (attempt + 1))
                    continue
                log.warning("tavily.search_failed", error=str(exc))
                self._cache[query] = []
                return []

        passages = [
            Passage(
                content=r.get("content", ""),
                source_path=r.get("url"),
                filename=r.get("title"),
                score=r.get("score"),
                metadata={"url": r.get("url"), "title": r.get("title"), "source": "tavily"},
            )
            for r in resp.get("results", [])
        ]
        log.info("tavily.search", query=guided, results=len(passages))
        self._cache[query] = passages
        return passages
