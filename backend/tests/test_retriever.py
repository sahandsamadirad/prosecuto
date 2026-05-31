"""Phase 2 tests: retriever, critics, Tavily fallback, and the loop cap.

Everything runs offline with fakes injected — no NVIDIA / Tavily calls. Covers
IMPLEMENTATION_PLAN.md Phase 2 "done when":

* query → passages with metadata;
* irrelevant passages trigger Tavily;
* each critic returns the expected Pydantic structure;
* the 2-retry generation cap is enforced (grounding always False → no infinite loop).
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from app.rag.critic import AdequacyGrade, Critics, GroundingGrade, RelevanceGrade
from app.rag.results import Passage
from app.rag.retriever import IdentityReranker, ProsecutoRetriever
from app.rag.self_rag import arun_self_rag, make_async_llm_generator, make_llm_generator, run_self_rag
from app.rag.tavily_fallback import TavilyFallback


# --- Fakes ----------------------------------------------------------------


class FakeVectorStore:
    def __init__(self, docs_with_scores):
        self._data = docs_with_scores

    def similarity_search_with_score(self, query, k=8, filter=None):
        return self._data[:k]


class FakeCritics:
    """Critics with scripted return values (no LLM)."""

    def __init__(self, relevant=True, grounded=True, adequate=True):
        self._relevant = relevant
        self._grounded = grounded
        self._adequate = adequate
        self.relevance_calls = 0
        self.grounding_calls = 0

    def grade_relevance(self, query, passage):
        self.relevance_calls += 1
        return RelevanceGrade(relevant=self._relevant, reason="fake")

    async def agrade_relevance(self, query, passage):
        return self.grade_relevance(query, passage)

    def grade_grounding(self, answer, passages):
        self.grounding_calls += 1
        return GroundingGrade(
            grounded=self._grounded,
            unsupported_claims=[] if self._grounded else ["x"],
        )

    async def agrade_grounding(self, answer, passages):
        return self.grade_grounding(answer, passages)

    def grade_adequacy(self, question, answer):
        return AdequacyGrade(adequate=self._adequate, missing=[] if self._adequate else ["y"])

    async def agrade_adequacy(self, question, answer):
        return self.grade_adequacy(question, answer)


class FakeTavily(TavilyFallback):
    def __init__(self, results):
        super().__init__(client=object())  # non-None so search() proceeds
        self._results = results

    def search(self, query):
        if query in self._cache:
            return self._cache[query]
        self._cache[query] = list(self._results)
        return self._cache[query]


def _doc(text, **meta):
    base = {"source_path": "hta_s144.txt", "filename": "hta_s144.txt", "chunk_index": 0}
    base.update(meta)
    return Document(page_content=text, metadata=base)


# --- Critic structure tests ----------------------------------------------


def test_critics_build_and_grade_with_fake_llm():
    """Critics wire prompt | llm.with_structured_output and return the models."""
    from langchain_core.runnables import RunnableLambda

    class FakeLLM:
        def with_structured_output(self, schema):
            samples = {
                RelevanceGrade: RelevanceGrade(relevant=True, reason="r"),
                GroundingGrade: GroundingGrade(grounded=True, unsupported_claims=[]),
                AdequacyGrade: AdequacyGrade(adequate=True, missing=[]),
            }
            value = samples[schema]
            return RunnableLambda(lambda _: value)

    critics = Critics(FakeLLM())
    assert isinstance(critics.grade_relevance("q", "p"), RelevanceGrade)
    assert isinstance(critics.grade_grounding("a", ["p"]), GroundingGrade)
    assert isinstance(critics.grade_adequacy("q", "a"), AdequacyGrade)


# --- Retriever tests ------------------------------------------------------


def test_retrieve_returns_passages_with_metadata():
    vs = FakeVectorStore([(_doc("red light offence s144"), 0.1)])
    retr = ProsecutoRetriever(vs, IdentityReranker(), FakeCritics(relevant=True), FakeTavily([]))
    res = retr.retrieve("red light deadline", k=8, n=4)
    assert res.source == "rag"
    assert len(res.passages) == 1
    p = res.passages[0]
    assert p.filename == "hta_s144.txt"
    assert p.metadata["source_path"] == "hta_s144.txt"


def test_irrelevant_passages_trigger_tavily():
    vs = FakeVectorStore([(_doc("totally unrelated text"), 0.9)])
    tav = FakeTavily([Passage(content="web result", source_path="http://x", filename="x")])
    retr = ProsecutoRetriever(vs, IdentityReranker(), FakeCritics(relevant=False), tav)
    res = retr.retrieve("red light deadline")
    assert res.source == "tavily"
    assert res.passages[0].content == "web result"


def test_empty_chroma_and_no_tavily_returns_none_source():
    retr = ProsecutoRetriever(FakeVectorStore([]), IdentityReranker(), FakeCritics(), FakeTavily([]))
    res = retr.retrieve("anything")
    assert res.source == "none"
    assert res.passages == []


def test_grade_false_skips_relevance_critic():
    vs = FakeVectorStore([(_doc("x"), 0.1)])
    critics = FakeCritics(relevant=True)
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, FakeTavily([]))
    retr.retrieve("q", grade=False)
    assert critics.relevance_calls == 0  # raw retrieve, no grading


# --- Tavily cache ---------------------------------------------------------


def test_tavily_cache_is_session_scoped():
    tav = FakeTavily([Passage(content="r", source_path="u", filename="t")])
    first = tav.search("same query")
    second = tav.search("same query")
    assert first == second
    assert list(tav._cache.keys()) == ["same query"]


# --- Self-RAG loop cap ----------------------------------------------------


def test_loop_cap_enforced_when_grounding_always_false():
    """Grounding critic always False must NOT infinite loop; caps at max_retries."""
    vs = FakeVectorStore([(_doc("s144 text"), 0.1)])
    critics = FakeCritics(relevant=True, grounded=False, adequate=True)
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, FakeTavily([]))

    gen_calls = {"n": 0}

    def generate(query, passages, strict):
        gen_calls["n"] += 1
        return "an answer"

    res = run_self_rag("q", retr, generate, critics, max_retries=2)
    # initial attempt + 2 retries = 3 generations, then stop.
    assert gen_calls["n"] == 3
    assert res.retries == 2
    assert res.confidence == "low"


def test_self_rag_happy_path_high_confidence():
    vs = FakeVectorStore([(_doc("s144 text"), 0.1)])
    critics = FakeCritics(relevant=True, grounded=True, adequate=True)
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, FakeTavily([]))

    def generate(query, passages, strict):
        return "grounded answer"

    res = run_self_rag("q", retr, generate, critics, max_retries=2)
    assert res.confidence == "high"
    assert res.retries == 0
    assert res.source == "rag"


def test_self_rag_adequacy_failure_escalates_to_tavily():
    vs = FakeVectorStore([(_doc("s144 text"), 0.1)])
    critics = FakeCritics(relevant=True, grounded=True, adequate=False)
    tav = FakeTavily([Passage(content="web", source_path="u", filename="t")])
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, tav)

    def generate(query, passages, strict):
        return "answer"

    res = run_self_rag("q", retr, generate, critics, max_retries=2)
    assert res.source == "tavily"  # escalated


def test_make_llm_generator_uses_passages():
    from langchain_core.runnables import RunnableLambda

    class FakeMsg:
        content = "generated"

    fake_llm = RunnableLambda(lambda _: FakeMsg())
    gen = make_llm_generator(fake_llm)
    out = gen("q", [Passage(content="c", filename="f")], strict=False)
    assert out == "generated"

@pytest.mark.asyncio
async def test_aretrieve_parallelizes_grading():
    vs = FakeVectorStore([(_doc("p1"), 0.1), (_doc("p2"), 0.2)])
    critics = FakeCritics(relevant=True)
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, FakeTavily([]))
    res = await retr.aretrieve("q", k=8, n=2)
    assert len(res.passages) == 2
    assert critics.relevance_calls == 2


@pytest.mark.asyncio
async def test_arun_self_rag_happy_path():
    vs = FakeVectorStore([(_doc("s144 text"), 0.1)])
    critics = FakeCritics(relevant=True, grounded=True, adequate=True)
    retr = ProsecutoRetriever(vs, IdentityReranker(), critics, FakeTavily([]))

    async def generate(query, passages, strict):
        return "grounded answer"

    res = await arun_self_rag("q", retr, generate, critics, max_retries=2)
    assert res.confidence == "high"
    assert res.source == "rag"


@pytest.mark.asyncio
async def test_make_async_llm_generator_works():
    from langchain_core.runnables import RunnableLambda

    class FakeMsg:
        content = "generated"

    async def _aimp(x):
        return FakeMsg()

    fake_llm = RunnableLambda(_aimp)
    gen = make_async_llm_generator(fake_llm)
    out = await gen("q", [Passage(content="c", filename="f")], strict=False)
    assert out == "generated"
