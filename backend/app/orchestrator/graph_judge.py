"""Judge Mode orchestrator — single-judge question/answer mock hearing.

The old courtroom phase machine used Clerk, Crown, and Judge agents. The current
UX is intentionally simpler: one judge asks a question, waits for the defendant,
asks the next question, and eventually gives final feedback.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, AsyncIterator, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.orchestrator.state import CourtPhase, SessionState
from app.schemas.case import Turn

log = structlog.get_logger(__name__)

MAX_JUDGE_ANSWERS = 4
FINISH_TERMS = ("finish", "final", "verdict", "done", "end the hearing")


@dataclass
class JudgeCharacters:
    judge: BaseAgent


class JudgeGraphState(TypedDict, total=False):
    session: SessionState
    last_text: str
    emitted: Annotated[list[str], operator.add]


def _defence_answer_count(s: SessionState) -> int:
    return sum(1 for t in (s.court_transcript or []) if t.role == "user")


def _wants_finish(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.strip().lower()
    return any(term in normalized for term in FINISH_TERMS)


def route_judge_entry(gs: JudgeGraphState) -> str:
    return END if gs["session"].court_phase == CourtPhase.DONE else "judge_step"


def _make_judge_step(judge: BaseAgent):
    async def judge_step(gs: JudgeGraphState) -> dict:
        s = gs["session"]
        if s.court_phase in (None, CourtPhase.IDLE):
            s.court_phase = CourtPhase.QUESTIONING

        res = await judge.run(s)
        s = res.updated_state
        text = res.assistant_text

        s.add_turn("assistant", text, agent=judge.name)
        if s.court_transcript is None:
            s.court_transcript = []
        s.court_transcript.append(Turn(role="assistant", content=text, agent=judge.name))
        s.current_agent = judge.name
        if s.court_phase == CourtPhase.FINAL:
            s.court_phase = CourtPhase.DONE
        else:
            s.court_phase = CourtPhase.QUESTIONING
        s.touch()

        log.info("judge.question", phase=s.court_phase.value, speaker=judge.name)
        return {"session": s, "last_text": text, "emitted": [text]}

    return judge_step


def build_judge_graph(characters: JudgeCharacters, checkpointer=None):
    g = StateGraph(JudgeGraphState)
    g.add_node("judge_step", _make_judge_step(characters.judge))
    g.add_conditional_edges(START, route_judge_entry, {"judge_step": "judge_step", END: END})
    g.add_edge("judge_step", END)
    return g.compile(checkpointer=checkpointer)


async def astream_court_turn(
    graph,
    session: SessionState,
    user_message: str | None = None,
    thread_id: str | None = None,
) -> AsyncIterator[tuple[str, str, SessionState]]:
    """Drive one judge turn, yielding exactly one judge message when active."""
    if session.court_phase == CourtPhase.DONE:
        return

    if user_message:
        session.add_turn("user", user_message)
        if session.court_transcript is None:
            session.court_transcript = []
        session.court_transcript.append(Turn(role="user", content=user_message, agent="defence"))

    if _wants_finish(user_message) or _defence_answer_count(session) >= MAX_JUDGE_ANSWERS:
        session.court_phase = CourtPhase.FINAL
    elif session.court_phase in (None, CourtPhase.IDLE):
        session.court_phase = CourtPhase.QUESTIONING

    config = {"configurable": {"thread_id": thread_id or session.session_id}}
    inputs: JudgeGraphState = {"session": session, "emitted": []}

    async for update in graph.astream(inputs, config=config, stream_mode="updates"):
        for _node, payload in update.items():
            yield payload["session"].current_agent, payload.get("last_text", ""), payload["session"]


def get_judge_characters(llm=None, retriever=None) -> JudgeCharacters:
    from app.agents.judge import JudgeAgent

    if llm is None:
        from app.llm import get_chat_llm

        # Courtroom characters generate scripted speech — no CoT needed.
        llm = get_chat_llm(temperature=0.0, thinking=False)
    if retriever is None:
        from app.rag.retriever import get_retriever

        retriever = get_retriever()

    return JudgeCharacters(judge=JudgeAgent(llm, retriever=retriever))


def get_judge_graph(llm=None, retriever=None, checkpointer=None):
    chars = get_judge_characters(llm, retriever)
    if checkpointer is None:
        from app.orchestrator.graph_lawyer import get_checkpointer

        checkpointer = get_checkpointer()
    return build_judge_graph(chars, checkpointer)
