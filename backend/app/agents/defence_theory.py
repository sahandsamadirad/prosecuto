"""Defence Theory Agent — the heaviest agent (ARCHITECTURE.md section 5 / Phase 5 step 6).

Runs the full Self-RAG flow (retrieve → rerank → relevance/grounding/adequacy
critics, with Tavily fallback and the retry cap) to assemble a grounded legal
basis, then emits the path-appropriate package via structured output:

    early_resolution → ERPackage
    screening_review → ScreeningReviewPackage
    trial            → TrialPrepPackage

Tags the package preliminary when disclosure was requested but not yet received,
and carries the Self-RAG confidence through to the package.
"""

from __future__ import annotations

import asyncio

import structlog

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import DEFENCE_THEORY
from app.rag.results import Passage
from app.schemas.packages import (
    Citation,
    ERPackage,
    ScreeningReviewPackage,
    TrialPrepPackage,
)

log = structlog.get_logger(__name__)

_PACKAGE_BY_PATH = {
    "early_resolution": ERPackage,
    "screening_review": ScreeningReviewPackage,
    "trial": TrialPrepPackage,
}

_HUMAN = """{case}

Chosen path: {path}

## Grounded legal analysis
{analysis}

## Source passages
{context}

## Conversation so far
{history}

Produce the {path} preparation package using ONLY the grounded analysis and sources \
above. Be realistic and never promise an outcome."""


class DefenceTheoryAgent(BaseAgent):
    name = "defence_theory"
    character_prompt = DEFENCE_THEORY

    def __init__(self, llm, retriever=None, critics=None, generate=None) -> None:
        super().__init__(llm, retriever)
        self._critics = critics
        self._generate = generate

    @property
    def critics(self):
        if self._critics is None:
            from app.rag.critic import get_critics

            self._critics = get_critics(self.llm)
        return self._critics

    @property
    def generate(self):
        if self._generate is None:
            from app.rag.self_rag import make_async_llm_generator

            self._generate = make_async_llm_generator(self.llm)
        return self._generate

    async def run(self, state: SessionState) -> AgentResult:
        from app.rag.self_rag import arun_self_rag

        path = state.chosen_path or "trial"
        model = _PACKAGE_BY_PATH.get(path, TrialPrepPackage)
        query = self._build_query(state, path)

        # Self-RAG now supports async natively (Phase 11 parallelized critics).
        sr = await arun_self_rag(
            query, self.retriever, self.generate, self.critics
        )

        context = self._format_passages(sr.passages)
        package = await self.run_structured(
            model,
            _HUMAN,
            {
                "case": self.format_case(state),
                "path": path,
                "analysis": sr.answer,
                "context": context,
                "history": self.format_history(state),
            },
        )

        # Carry Self-RAG confidence + provenance into the package.
        package.confidence = sr.confidence
        package.is_preliminary = bool(state.disclosure_requested)
        package.citations = [
            Citation(
                claim="supporting source",
                source_filename=p.filename or (p.source_path or "unknown"),
                source_path=p.source_path,
            )
            for p in sr.passages
        ]
        if sr.source == "tavily":
            package.flags.append("used_web_fallback")
        if package.is_preliminary and "preliminary_pending_disclosure" not in package.flags:
            package.flags.append("preliminary_pending_disclosure")
        if sr.confidence == "low":
            package.flags.append("low_confidence_rag")

        self._attach_package(state, path, package)
        state.current_agent = self.name
        state.touch()

        msg = (
            f"I've put together your {path.replace('_', ' ')} package. "
            f"My confidence in it is {sr.confidence}."
            + (" It's preliminary until your disclosure comes back." if package.is_preliminary else "")
        )
        return AgentResult(updated_state=state, assistant_text=msg, data=package)

    # --- helpers ----------------------------------------------------------

    def _build_query(self, state: SessionState, path: str) -> str:
        sub = state.diagnosis.sub_type if state.diagnosis else "red light camera"
        return (
            f"legitimate defences, legal arguments, and anticipated Crown evidence for a "
            f"{sub} red light camera ticket in Ontario pursued via {path.replace('_', ' ')}"
        )

    @staticmethod
    def _format_passages(passages: list[Passage]) -> str:
        if not passages:
            return "(no sources retrieved)"
        return "\n\n---\n\n".join(
            f"[{p.filename or p.source_path}] {p.content}" for p in passages
        )

    @staticmethod
    def _attach_package(state: SessionState, path: str, package) -> None:
        if path == "early_resolution":
            state.er_package = package
        elif path == "screening_review":
            state.screening_review_package = package
        else:
            state.trial_prep_package = package
