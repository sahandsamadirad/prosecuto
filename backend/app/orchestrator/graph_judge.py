"""Judge Mode orchestrator — the court state machine (ARCHITECTURE.md §12, Phase 10).

A linear progression of court phases:

    IDLE → CLERK_CALL_TO_ORDER → CLERK_OATH → JUDGE_OPEN → CROWN_OPENING
         → DEFENCE_OPENING*       → CROWN_CASE → DEFENCE_CROSS_CROWN*
         → DEFENCE_CASE*          → CROWN_CROSS_DEFENCE(†) → CROWN_CLOSING
         → DEFENCE_CLOSING*       → VERDICT → FEEDBACK → DONE

    *  "waits on user": the graph pauses and the user (defendant) speaks next.
    †  Crown cross-examines, then pauses for the defendant's answer.

Implemented as a single self-looping ``court_step`` node that speaks the current
phase's character and advances ``court_phase``, ending when it reaches a phase
that requires the user (state-derived, so reload-and-resume works for free —
mirrors the Lawyer graph). Each beat is appended to both the overall transcript
and the dedicated ``court_transcript``.
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

# Ordered court phases (IDLE maps onto the first beat).
COURT_ORDER = [
    CourtPhase.CLERK_CALL_TO_ORDER,
    CourtPhase.CLERK_OATH,
    CourtPhase.JUDGE_OPEN,
    CourtPhase.CROWN_OPENING,
    CourtPhase.DEFENCE_OPENING,
    CourtPhase.CROWN_CASE,
    CourtPhase.DEFENCE_CROSS_CROWN,
    CourtPhase.DEFENCE_CASE,
    CourtPhase.CROWN_CROSS_DEFENCE,
    CourtPhase.CROWN_CLOSING,
    CourtPhase.DEFENCE_CLOSING,
    CourtPhase.VERDICT,
    CourtPhase.FEEDBACK,
    CourtPhase.DONE,
]

# Phases where the user (defendant) speaks — the graph pauses here.
USER_PHASES = {
    CourtPhase.DEFENCE_OPENING,
    CourtPhase.DEFENCE_CROSS_CROWN,
    CourtPhase.DEFENCE_CASE,
    CourtPhase.DEFENCE_CLOSING,
}

# Agent phases after which we still pause for a user response.
PAUSE_AFTER = {CourtPhase.CROWN_CROSS_DEFENCE}

# Which character speaks each agent phase.
SPEAKER = {
    CourtPhase.CLERK_CALL_TO_ORDER: "clerk",
    CourtPhase.CLERK_OATH: "clerk",
    CourtPhase.JUDGE_OPEN: "judge",
    CourtPhase.CROWN_OPENING: "crown",
    CourtPhase.CROWN_CASE: "crown",
    CourtPhase.CROWN_CROSS_DEFENCE: "crown",
    CourtPhase.CROWN_CLOSING: "crown",
    CourtPhase.VERDICT: "judge",
    CourtPhase.FEEDBACK: "judge",
}


def next_phase(phase: CourtPhase) -> CourtPhase:
    if phase == CourtPhase.DONE:
        return CourtPhase.DONE
    idx = COURT_ORDER.index(phase)
    return COURT_ORDER[idx + 1] if idx + 1 < len(COURT_ORDER) else CourtPhase.DONE


@dataclass
class JudgeCharacters:
    clerk: BaseAgent
    judge: BaseAgent
    prosecutor: BaseAgent


class JudgeGraphState(TypedDict, total=False):
    session: SessionState
    last_text: str
    emitted: Annotated[list[str], operator.add]
    just_ran: CourtPhase


# --- Routers --------------------------------------------------------------


def route_judge_entry(gs: JudgeGraphState) -> str:
    phase = gs["session"].court_phase or CourtPhase.IDLE
    if phase in USER_PHASES or phase == CourtPhase.DONE:
        return END
    return "court_step"


def after_court_step(gs: JudgeGraphState) -> str:
    nxt = gs["session"].court_phase
    if nxt == CourtPhase.DONE or nxt in USER_PHASES:
        return END
    if gs.get("just_ran") in PAUSE_AFTER:
        return END  # crown finished cross — wait for the defendant's answer
    return "court_step"


# --- Node -----------------------------------------------------------------


def _make_court_step(characters: JudgeCharacters):
    by_speaker = {
        "clerk": characters.clerk,
        "judge": characters.judge,
        "crown": characters.prosecutor,
    }

    async def court_step(gs: JudgeGraphState) -> dict:
        s = gs["session"]
        phase = s.court_phase or CourtPhase.IDLE
        if phase == CourtPhase.IDLE:
            phase = CourtPhase.CLERK_CALL_TO_ORDER

        character = by_speaker[SPEAKER[phase]]
        s.court_phase = phase  # ensure the agent sees the phase it's speaking
        res = await character.run(s)
        s = res.updated_state
        text = res.assistant_text

        s.add_turn("assistant", text, agent=character.name)
        if s.court_transcript is None:
            s.court_transcript = []
        s.court_transcript.append(Turn(role="assistant", content=text, agent=character.name))
        s.current_agent = character.name
        s.court_phase = next_phase(phase)
        s.touch()

        log.info("judge.beat", phase=phase.value, speaker=character.name)
        return {"session": s, "last_text": text, "emitted": [text], "just_ran": phase}

    return court_step


def build_judge_graph(characters: JudgeCharacters, checkpointer=None):
    g = StateGraph(JudgeGraphState)
    g.add_node("court_step", _make_court_step(characters))
    g.add_conditional_edges(START, route_judge_entry, {"court_step": "court_step", END: END})
    g.add_conditional_edges("court_step", after_court_step, {"court_step": "court_step", END: END})
    return g.compile(checkpointer=checkpointer)


# --- Turn driver ----------------------------------------------------------


async def astream_court_turn(
    graph,
    session: SessionState,
    user_message: str | None = None,
    thread_id: str | None = None,
) -> AsyncIterator[tuple[str, str, SessionState]]:
    """Drive one court turn.

    With no ``user_message`` (trial start), runs the opening beats until the
    defendant's first turn. Otherwise records the defendant's words, advances past
    the user phase, and runs the next run of character beats.
    """
    if user_message:
        session.add_turn("user", user_message)
        if session.court_transcript is None:
            session.court_transcript = []
        session.court_transcript.append(
            Turn(role="user", content=user_message, agent="defence")
        )
        if session.court_phase in USER_PHASES:
            session.court_phase = next_phase(session.court_phase)

    config = {"configurable": {"thread_id": thread_id or session.session_id}}
    inputs: JudgeGraphState = {"session": session, "emitted": []}

    async for update in graph.astream(inputs, config=config, stream_mode="updates"):
        for _node, payload in update.items():
            yield payload["session"].current_agent, payload.get("last_text", ""), payload["session"]


def get_judge_characters(llm=None, retriever=None) -> JudgeCharacters:
    from app.agents.clerk import CourtClerkAgent
    from app.agents.judge import JudgeAgent
    from app.agents.prosecutor import CrownProsecutorAgent

    if llm is None:
        from app.llm import get_chat_llm

        llm = get_chat_llm(temperature=0.3)  # a little warmth for courtroom voices
    if retriever is None:
        from app.rag.retriever import get_retriever

        retriever = get_retriever()

    return JudgeCharacters(
        clerk=CourtClerkAgent(llm),
        judge=JudgeAgent(llm, retriever=retriever),
        prosecutor=CrownProsecutorAgent(llm, retriever=retriever),
    )


def get_judge_graph(llm=None, retriever=None, checkpointer=None):
    chars = get_judge_characters(llm, retriever)
    if checkpointer is None:
        from app.orchestrator.graph_lawyer import get_checkpointer

        checkpointer = get_checkpointer()
    return build_judge_graph(chars, checkpointer)
