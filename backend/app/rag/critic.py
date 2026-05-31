"""Self-RAG critics — three graders backed by Nemotron + structured output.

Implements ARCHITECTURE.md section 6 "Critic Implementation" and mirrors the
reference Self-RAG ``graph/chains/{retrieval,hallucination,answer}_grader.py``:
each grader is ``prompt | llm.with_structured_output(PydanticModel)``.

1. Relevance critic   — passage relevant to the query?
2. Grounding critic   — answer supported by the passages? (hallucination check)
3. Answer-adequacy    — does the answer fully resolve the question?

All three are deterministic (temperature 0). The ``Critics`` object is built
once per process via :func:`get_critics`; tests inject a fake LLM instead.
"""

from __future__ import annotations

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)


# --- Structured grader outputs (ARCHITECTURE.md section 6) ----------------


class RelevanceGrade(BaseModel):
    """Is a retrieved passage relevant to the user's query?"""

    relevant: bool = Field(description="True if the passage helps answer the query.")
    reason: str = Field(description="Short justification for the decision.")


class GroundingGrade(BaseModel):
    """Is the generated answer supported by the retrieved passages?"""

    grounded: bool = Field(
        description="True if every claim in the answer is supported by the passages."
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims in the answer not backed by the passages.",
    )


class AdequacyGrade(BaseModel):
    """Does the answer fully resolve the user's question?"""

    adequate: bool = Field(description="True if the answer fully addresses the question.")
    missing: list[str] = Field(
        default_factory=list,
        description="Aspects of the question left unanswered.",
    )


# --- Prompts --------------------------------------------------------------

_RELEVANCE_SYS = (
    "You are a grader assessing the relevance of a retrieved legal passage to a "
    "user question about Ontario red light camera tickets. If the passage contains "
    "keywords or legal meaning related to the question, grade it relevant. Be lenient: "
    "the goal is to filter out clearly unrelated passages, not to require a perfect match."
)

_GROUNDING_SYS = (
    "You are a grader assessing whether an answer is grounded in / supported by a set "
    "of legal source passages. Grade 'grounded' true only if every factual and legal "
    "claim in the answer is supported by the passages. List any claim that is not "
    "supported. Do not reward fluency — only grounding in the provided sources."
)

_ADEQUACY_SYS = (
    "You are a grader assessing whether an answer resolves a user's question about an "
    "Ontario red light camera ticket. Grade 'adequate' true only if the answer "
    "addresses what was asked. List what is still missing if it does not."
)


class Critics:
    """The three Self-RAG graders, sharing one structured-output LLM."""

    def __init__(self, llm) -> None:
        self._relevance = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", _RELEVANCE_SYS),
                    ("human", "Passage:\n{passage}\n\nQuestion: {query}"),
                ]
            )
            | llm.with_structured_output(RelevanceGrade)
        )
        self._grounding = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", _GROUNDING_SYS),
                    ("human", "Source passages:\n{passages}\n\nAnswer:\n{answer}"),
                ]
            )
            | llm.with_structured_output(GroundingGrade)
        )
        self._adequacy = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", _ADEQUACY_SYS),
                    ("human", "Question: {question}\n\nAnswer:\n{answer}"),
                ]
            )
            | llm.with_structured_output(AdequacyGrade)
        )

    def grade_relevance(self, query: str, passage: str) -> RelevanceGrade:
        return self._relevance.invoke({"query": query, "passage": passage})

    async def agrade_relevance(self, query: str, passage: str) -> RelevanceGrade:
        return await self._relevance.ainvoke({"query": query, "passage": passage})

    def grade_grounding(self, answer: str, passages: list[str]) -> GroundingGrade:
        joined = "\n\n---\n\n".join(passages)
        return self._grounding.invoke({"answer": answer, "passages": joined})

    async def agrade_grounding(self, answer: str, passages: list[str]) -> GroundingGrade:
        joined = "\n\n---\n\n".join(passages)
        return await self._grounding.ainvoke({"answer": answer, "passages": joined})

    def grade_adequacy(self, question: str, answer: str) -> AdequacyGrade:
        return self._adequacy.invoke({"question": question, "answer": answer})

    async def agrade_adequacy(self, question: str, answer: str) -> AdequacyGrade:
        return await self._adequacy.ainvoke({"question": question, "answer": answer})


def get_critics(llm=None) -> Critics:
    """Build the critics with the default Nemotron LLM (or an injected one)."""
    if llm is None:
        from app.llm import get_chat_llm

        llm = get_chat_llm(temperature=0.0)
    return Critics(llm)
