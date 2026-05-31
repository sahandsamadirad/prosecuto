"""Lawyer Mode orchestrator — the LangGraph composing the six agents.

Implements ARCHITECTURE.md section 12 / IMPLEMENTATION_PLAN.md Phase 6:

    START
      → required_info        (loops per user turn until the checklist is complete)
      → ticket_diagnosis
      → procedure_map        → END (waits for the user to choose a path)
      → [user sets chosen_path]
          ├─ pay                                  → END
          └─ early_resolution/screening_review/trial:
                 → sufficient_data
                       ├─ False → disclosure → defence_theory → END
                       └─ True  →               defence_theory → END

Resumability is **state-derived**: a conditional entry router (`route_entry`)
picks the resume node from how far the :class:`SessionState` has progressed, so
reloading persisted state continues from exactly the right node — no separate
checkpoint needed (a checkpointer is still attached for LangGraph-native resume).

The graph state is a thin TypedDict wrapping a single ``session`` channel so node
returns overwrite cleanly; ``emitted`` accumulates the per-node assistant texts
for streaming to TTS.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, AsyncIterator, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.orchestrator.state import SessionState

log = structlog.get_logger(__name__)


class LawyerGraphState(TypedDict, total=False):
    session: SessionState
    last_text: str
    emitted: Annotated[list[str], operator.add]


@dataclass
class LawyerAgents:
    """The six agent instances the graph nodes invoke."""

    required_info: BaseAgent
    ticket_diagnosis: BaseAgent
    procedure_map: BaseAgent
    sufficient_data: BaseAgent
    disclosure: BaseAgent
    defence_theory: BaseAgent


# --- Routers --------------------------------------------------------------

# Deterministic cap: at most this many user dialogs before we stop gathering
# and produce the final defence package (ARCHITECTURE behaviour / demo rule).
MAX_LAWYER_DIALOGS = 5
FORCE_FINAL_PACKAGE_FLAG = "force_final_package"


def _user_turn_count(s: SessionState) -> int:
    return sum(1 for t in s.transcript if t.role == "user")


def _force_final_path(s: SessionState) -> None:
    if s.chosen_path is None or s.chosen_path == "pay":
        s.chosen_path = "early_resolution"


def route_entry(gs: LawyerGraphState) -> str:
    """Pick the resume node from how far the session has progressed."""
    s = gs["session"]
    td = s.ticket_details

    # Hard dialog cap → jump straight to the final package, deterministically.
    if s.finalized_package() is not None:
        return END
    if FORCE_FINAL_PACKAGE_FLAG in s.flags:
        _force_final_path(s)
        return "defence_theory"
    if _user_turn_count(s) >= MAX_LAWYER_DIALOGS:
        _force_final_path(s)
        return "defence_theory"

    if td is None or not td.is_complete():
        return "required_info"
    if s.diagnosis is None:
        return "ticket_diagnosis"
    if s.chosen_path is None:
        # Present options once; then wait (END) for the user's choice.
        return "procedure_map" if s.current_agent != "procedure_map" else END
    if s.chosen_path == "pay":
        return END
    if s.finalized_package() is not None:
        return END
    if s.sufficient_data is None:
        return "sufficient_data"
    if s.sufficient_data is False and not s.disclosure_requested:
        return "disclosure"
    return "defence_theory"


def after_required_info(gs: LawyerGraphState) -> str:
    s = gs["session"]
    if s.ticket_details and s.ticket_details.is_complete():
        return "ticket_diagnosis"
    return END  # checklist incomplete → wait for the next user turn


def after_sufficient_data(gs: LawyerGraphState) -> str:
    return "defence_theory" if gs["session"].sufficient_data else "disclosure"


# --- Graph construction ---------------------------------------------------


def _make_node(agent: BaseAgent):
    async def node(gs: LawyerGraphState) -> dict:
        res = await agent.run(gs["session"])
        log.info("graph.node", agent=agent.name, session_id=res.updated_state.session_id)
        return {
            "session": res.updated_state,
            "last_text": res.assistant_text,
            "emitted": [res.assistant_text],
        }

    return node


def build_lawyer_graph(agents: LawyerAgents, checkpointer=None):
    """Compile the Lawyer Mode graph from injected agent instances."""
    g = StateGraph(LawyerGraphState)

    g.add_node("required_info", _make_node(agents.required_info))
    g.add_node("ticket_diagnosis", _make_node(agents.ticket_diagnosis))
    g.add_node("procedure_map", _make_node(agents.procedure_map))
    g.add_node("sufficient_data", _make_node(agents.sufficient_data))
    g.add_node("disclosure", _make_node(agents.disclosure))
    g.add_node("defence_theory", _make_node(agents.defence_theory))

    node_names = [
        "required_info",
        "ticket_diagnosis",
        "procedure_map",
        "sufficient_data",
        "disclosure",
        "defence_theory",
    ]
    g.add_conditional_edges(START, route_entry, {n: n for n in node_names} | {END: END})

    g.add_conditional_edges(
        "required_info",
        after_required_info,
        {"ticket_diagnosis": "ticket_diagnosis", END: END},
    )
    g.add_edge("ticket_diagnosis", "procedure_map")
    g.add_edge("procedure_map", END)  # wait for the user's path choice
    g.add_conditional_edges(
        "sufficient_data",
        after_sufficient_data,
        {"disclosure": "disclosure", "defence_theory": "defence_theory"},
    )
    g.add_edge("disclosure", "defence_theory")
    g.add_edge("defence_theory", END)

    return g.compile(checkpointer=checkpointer)


# --- Turn driver (used by the WS layer) -----------------------------------


async def astream_turn(
    graph,
    session: SessionState,
    user_message: str,
    thread_id: str | None = None,
) -> AsyncIterator[tuple[str, str, SessionState]]:
    """Drive one conversational turn, yielding (node_name, assistant_text, session).

    Appends the user's message, then streams each node's assistant text as it is
    produced so the WS layer can push it to TTS immediately (ARCHITECTURE §10
    first-sentence kickoff).
    """
    session.add_turn("user", user_message)
    config = {"configurable": {"thread_id": thread_id or session.session_id}}
    inputs: LawyerGraphState = {"session": session, "emitted": []}

    async for update in graph.astream(inputs, config=config, stream_mode="updates"):
        for node_name, payload in update.items():
            updated = payload["session"]
            text = payload.get("last_text", "")
            if text:
                updated.add_turn("assistant", text, agent=updated.current_agent)
            yield node_name, text, updated


def get_checkpointer():
    """MemorySaver in dev; RedisSaver if the optional package is available."""
    try:
        from langgraph.checkpoint.redis import RedisSaver  # type: ignore

        from app.config import settings

        return RedisSaver.from_conn_string(settings.redis_url)
    except Exception:  # noqa: BLE001 — fall back to in-memory checkpointing
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


def get_lawyer_agents(llm=None, retriever=None) -> LawyerAgents:
    """Build the six real agents sharing one LLM and retriever."""
    from app.agents.defence_theory import DefenceTheoryAgent
    from app.agents.disclosure import DisclosureRequestAgent
    from app.agents.procedure_map import ProcedureMapAgent
    from app.agents.required_info import RequiredInfoAgent
    from app.agents.sufficient_data import SufficientDataAgent
    from app.agents.ticket_diagnosis import TicketDiagnosisAgent

    if llm is None:
        from app.llm import get_chat_llm

        llm_think = get_chat_llm(temperature=0, thinking=True)
        llm_fast = get_chat_llm(temperature=0, thinking=False)
    else:
        llm_think = llm
        llm_fast = llm
    if retriever is None:
        from app.rag.retriever import get_retriever

        retriever = get_retriever()

    return LawyerAgents(
        required_info=RequiredInfoAgent(llm_fast),
        ticket_diagnosis=TicketDiagnosisAgent(llm_think, retriever=retriever),
        procedure_map=ProcedureMapAgent(llm_think, retriever=retriever),
        sufficient_data=SufficientDataAgent(llm_fast),
        disclosure=DisclosureRequestAgent(llm_think, retriever=retriever),
        defence_theory=DefenceTheoryAgent(llm_think, retriever=retriever),
    )


def get_lawyer_graph(llm=None, retriever=None, checkpointer=None):
    """Convenience: build agents + compile the graph with a checkpointer."""
    agents = get_lawyer_agents(llm, retriever)
    return build_lawyer_graph(agents, checkpointer or get_checkpointer())
