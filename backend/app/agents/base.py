"""BaseAgent — the common shape for every Lawyer/Judge Mode agent.

Each agent is a single structured-output LLM call (ARCHITECTURE.md section 5),
invoked by the orchestrator with the full :class:`SessionState`. Agents read the
recent transcript + the populated case file from state so the user never repeats
themselves, then return an :class:`AgentResult` carrying the updated state and
the text the avatar will speak next.

Agents never call each other — only the orchestrator routes between them.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate

# Markdown artifacts a reasoning model sometimes emits despite instructions —
# stripped so spoken (TTS) output doesn't read symbols aloud.
_MD_BOLD = re.compile(r"(\*\*|__)(.*?)\1", re.DOTALL)
_MD_HEADER = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")
_MD_BULLET = re.compile(r"(?m)^\s{0,3}[-*]\s+")
_MD_TICKS = re.compile(r"`+")
_BLANKLINES = re.compile(r"\n{3,}")


def to_speech(text: str) -> str:
    """Flatten light markdown into plain prose for the voice pipeline."""
    text = _MD_BOLD.sub(r"\2", text)
    text = _MD_HEADER.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_TICKS.sub("", text)
    return _BLANKLINES.sub("\n\n", text).strip()

from app.orchestrator.state import SessionState
from app.prompts.base import BASE_SYSTEM_PROMPT
from app.schemas.case import TicketDetails


@dataclass
class AgentResult:
    """What every agent returns."""

    updated_state: SessionState
    assistant_text: str
    data: object | None = None  # the agent's structured output, for inspection/tests


class BaseAgent(ABC):
    name: str = "base"
    character_prompt: str = ""
    # Set to False on agents that don't need chain-of-thought (scripted speech,
    # form filling, binary gates). Injects /no_think into the system prompt so
    # the Nemotron Super chat template skips the <think> block entirely.
    thinking: bool = True

    def __init__(self, llm, retriever=None) -> None:
        self.llm = llm
        self.retriever = retriever

    @property
    def system_prompt(self) -> str:
        prefix = "" if self.thinking else "/no_think\n\n"
        return prefix + BASE_SYSTEM_PROMPT + "\n\n" + self.character_prompt

    @abstractmethod
    async def run(self, state: SessionState) -> AgentResult: ...

    # --- Shared prompt helpers --------------------------------------------

    def format_history(self, state: SessionState, k: int = 10) -> str:
        """Conversation window in the ARCHITECTURE §9 format."""
        turns = state.recent_transcript(k)
        if not turns:
            return "(no conversation yet)"
        lines = []
        for t in turns:
            ts = t.timestamp.strftime("%H:%M:%S")
            lines.append(f"[{t.role}, {ts}] {t.content}")
        return "\n".join(lines)

    def format_case(self, state: SessionState) -> str:
        """The 'Known case details' block threaded into every prompt."""
        td = state.ticket_details or TicketDetails()
        lines = ["## Known case details"]
        fields = {
            "Ticket type": td.ticket_type,
            "Ticket date": td.ticket_date,
            "Intersection": td.intersection,
            "Municipality": td.municipality,
            "Registered owner": td.vehicle_owner,
            "Who was driving": td.who_was_driving,
            "Ticket number": td.ticket_number,
            "Fine amount": td.fine_amount,
            "Deadline date": td.deadline_date,
        }
        for label, val in fields.items():
            lines.append(f"- {label}: {val if val is not None else 'TBD'}")
        if state.diagnosis:
            d = state.diagnosis
            lines.append(f"- Diagnosis: {d.sub_type} ({d.deadline_status})")
        if state.chosen_path:
            lines.append(f"- Chosen path: {state.chosen_path}")
        return "\n".join(lines)

    async def retrieve_context(self, query: str, k: int = 8, n: int = 4, filters: dict | None = None) -> str:
        """Retrieve and format passages for a prompt; '(no sources)' if none."""
        if self.retriever is None:
            return "(no sources retrieved)"
        result = await self.retriever.aretrieve(query, k=k, n=n, filters=filters)
        if not result.passages:
            return "(no sources retrieved)"
        return "\n\n---\n\n".join(
            f"[{p.filename or p.source_path}] {p.content}" for p in result.passages
        )

    async def run_structured(self, output_model, human_template: str, variables: dict):
        """Build ``system + human`` prompt and invoke with structured output."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", self.system_prompt), ("human", human_template)]
        )
        chain = prompt | self.llm.with_structured_output(output_model)
        return await chain.ainvoke(variables)

    async def generate_text(self, human_template: str, variables: dict) -> str:
        """Free-text generation (for speaking characters that don't need a schema)."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", self.system_prompt), ("human", human_template)]
        )
        msg = await (prompt | self.llm).ainvoke(variables)
        return to_speech(getattr(msg, "content", str(msg)))
