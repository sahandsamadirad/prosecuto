"""Self-RAG generation loop (ARCHITECTURE.md section 6).

Ties the retriever and critics together into the grounded-generation flow used
by every agent that touches the corpus:

    retrieve → generate → grounding critic
        ├─ grounded   → adequacy critic
        │                   ├─ adequate     → return
        │                   └─ not adequate → Tavily fallback → regenerate once
        └─ not grounded → regenerate (stricter)   [hard cap: MAX_RAG_RETRIES]

The loop safeguard is non-negotiable: generation is retried at most
``settings.max_rag_retries`` times. After the cap we return what we have with
``confidence="low"`` — never an infinite loop. Mirrors the loop-cap pattern from
the reference ``langgraph`` / self-rag repo.
"""

from __future__ import annotations

from typing import Callable, Literal, Protocol

import structlog
from pydantic import BaseModel, Field

from app.config import settings
from app.rag.critic import Critics
from app.rag.results import Passage, RetrievalSource

log = structlog.get_logger(__name__)

# A generator takes (query, passages, strict) and returns the answer text.
# ``strict`` is True on a retry so the agent prompt can tighten grounding.
Generator = Callable[[str, list[Passage], bool], str]


class _Retriever(Protocol):
    def retrieve(self, query: str, **kwargs): ...
    def _tavily_result(self, query: str): ...


class SelfRAGResult(BaseModel):
    """Outcome of a Self-RAG generation run."""

    query: str
    answer: str
    passages: list[Passage] = Field(default_factory=list)
    source: RetrievalSource = "none"
    confidence: Literal["high", "medium", "low"] = "high"
    retries: int = 0
    unsupported_claims: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


def run_self_rag(
    query: str,
    retriever: _Retriever,
    generate: Generator,
    critics: Critics,
    max_retries: int | None = None,
    k: int = 8,
    n: int = 4,
    filters: dict | None = None,
) -> SelfRAGResult:
    """Run the full Self-RAG flow with the hard retry cap."""
    max_retries = settings.max_rag_retries if max_retries is None else max_retries

    retrieval = retriever.retrieve(query, k=k, n=n, filters=filters)
    passages = retrieval.passages
    source: RetrievalSource = retrieval.source
    tried_tavily = source == "tavily"

    # If retrieval found nothing at all, we still answer (low confidence).
    answer, grounding, retries = _grounded_generation(
        query, passages, generate, critics, max_retries
    )
    confidence: Literal["high", "medium", "low"] = "high" if grounding.grounded else "low"

    # Adequacy gate — escalate to Tavily once if the answer is incomplete.
    adequacy = critics.grade_adequacy(query, answer)
    if not adequacy.adequate and not tried_tavily:
        log.info("self_rag.adequacy_fail_escalate", query=query, missing=adequacy.missing)
        tav = retriever._tavily_result(query)
        if tav.passages:
            passages = tav.passages
            source = "tavily"
            tried_tavily = True
            answer, grounding, more = _grounded_generation(
                query, passages, generate, critics, max_retries, strict_first=True
            )
            retries += more
            confidence = "medium" if grounding.grounded else "low"
            adequacy = critics.grade_adequacy(query, answer)

    if not adequacy.adequate and confidence == "high":
        confidence = "medium"

    result = SelfRAGResult(
        query=query,
        answer=answer,
        passages=passages,
        source=source,
        confidence=confidence,
        retries=retries,
        unsupported_claims=grounding.unsupported_claims,
        missing=adequacy.missing,
    )
    log.info(
        "self_rag.done",
        query=query,
        source=source,
        confidence=confidence,
        retries=retries,
    )
    return result


def _grounded_generation(
    query: str,
    passages: list[Passage],
    generate: Generator,
    critics: Critics,
    max_retries: int,
    strict_first: bool = False,
):
    """Generate, then retry on ungrounded output up to ``max_retries`` times.

    Returns ``(answer, GroundingGrade, retries_used)``. Guaranteed to terminate.
    """
    texts = [p.content for p in passages]
    attempt = 0
    while True:
        strict = strict_first or attempt > 0
        answer = generate(query, passages, strict)
        grounding = critics.grade_grounding(answer, texts)
        if grounding.grounded or attempt >= max_retries:
            if not grounding.grounded:
                log.warning("self_rag.cap_reached", query=query, retries=attempt)
            return answer, grounding, attempt
        attempt += 1
        log.info("self_rag.regenerate", query=query, attempt=attempt)


def make_llm_generator(llm) -> Generator:
    """Default answer generator: answer the query grounded in the passages."""
    from langchain_core.prompts import ChatPromptTemplate

    base_sys = (
        "You are a legal assistant for Ontario red light camera ticket disputes. "
        "Answer the question using ONLY the provided source passages. Cite the source "
        "filename for any legal claim. If the passages do not contain the answer, say so."
    )
    strict_sys = base_sys + (
        " Your previous answer included unsupported claims. Be conservative: state only "
        "what the passages directly support and omit anything you cannot ground."
    )

    def _generate(query: str, passages: list[Passage], strict: bool) -> str:
        sys = strict_sys if strict else base_sys
        ctx = "\n\n---\n\n".join(
            f"[{p.filename or p.source_path}]\n{p.content}" for p in passages
        ) or "(no passages retrieved)"
        prompt = ChatPromptTemplate.from_messages(
            [("system", sys), ("human", "Sources:\n{ctx}\n\nQuestion: {query}")]
        )
        msg = (prompt | llm).invoke({"ctx": ctx, "query": query})
        return getattr(msg, "content", str(msg))

    return _generate
