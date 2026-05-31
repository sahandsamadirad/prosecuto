"""Phase 6 tests: the Lawyer Mode LangGraph orchestrator.

Uses deterministic fake agents so the test exercises the graph wiring —
conditional routing, the wait-for-user loop, streaming order, and state-derived
resumability — not the LLM. Covers IMPLEMENTATION_PLAN.md Phase 6 "done when".
"""

from __future__ import annotations

from datetime import date

from langgraph.checkpoint.memory import MemorySaver

from app.agents.base import AgentResult
from app.orchestrator.graph_lawyer import (
    LawyerAgents,
    astream_turn,
    build_lawyer_graph,
)
from app.orchestrator.state import SessionState
from app.schemas.case import TicketDetails, TicketDiagnosis
from app.schemas.packages import DisclosurePackage, ERPackage


# --- Deterministic fake agents -------------------------------------------


def _complete_details() -> TicketDetails:
    return TicketDetails(
        ticket_type="camera_issued", ticket_date=date(2025, 11, 18), intersection="King & Bay",
        vehicle_owner="self", who_was_driving="self", ticket_number="RLC1",
        fine_amount=325.0, deadline_date=date(2026, 1, 1),
    )


class FakeAgent:
    def __init__(self, name, mutate, text):
        self.name = name
        self._mutate = mutate
        self._text = text

    async def run(self, state: SessionState) -> AgentResult:
        self._mutate(state)
        state.current_agent = self.name
        state.touch()
        return AgentResult(updated_state=state, assistant_text=self._text)


def _agents(complete=True, sufficient=True) -> LawyerAgents:
    def ri(s):
        s.ticket_details = _complete_details() if complete else TicketDetails(ticket_type="camera_issued")

    def diag(s):
        s.diagnosis = TicketDiagnosis(
            type="camera_issued", sub_type="amps_camera", is_red_light_camera=True,
            deadline_status="within_window", recap_text="camera ticket")

    def pm(s):
        pass  # just presents options

    def sd(s):
        s.sufficient_data = sufficient

    def disc(s):
        s.disclosure_requested = True
        s.disclosure_package = DisclosurePackage(request_text="disclose please")

    def dt(s):
        pkg = ERPackage(summary="ER plan")
        pkg.is_preliminary = bool(s.disclosure_requested)
        s.er_package = pkg

    return LawyerAgents(
        required_info=FakeAgent("required_info", ri, "Tell me about your ticket."),
        ticket_diagnosis=FakeAgent("ticket_diagnosis", diag, "This is a camera ticket."),
        procedure_map=FakeAgent("procedure_map", pm, "You can pursue early resolution or trial."),
        sufficient_data=FakeAgent("sufficient_data", sd, "Checking your case."),
        disclosure=FakeAgent("disclosure", disc, "Here is a disclosure request."),
        defence_theory=FakeAgent("defence_theory", dt, "Here is your package."),
    )


async def _drive(graph, session, msg):
    """Run one turn, return the list of (node, text) emitted."""
    out = []
    async for node, text, _ in astream_turn(graph, session, msg):
        out.append((node, text))
    return out


# --- Tests ----------------------------------------------------------------


async def test_full_flow_intake_to_package():
    graph = build_lawyer_graph(_agents(), MemorySaver())
    session = SessionState(session_id="s1", mode="lawyer")

    # Turn 1: intake completes → diagnosis → procedure_map, then waits.
    turn1 = await _drive(graph, session, "I got a red light camera ticket")
    assert [n for n, _ in turn1] == ["required_info", "ticket_diagnosis", "procedure_map"]
    assert session.diagnosis is not None
    assert session.chosen_path is None  # waiting for choice
    assert session.finalized_package() is None

    # User chooses a path (set externally / by the WS layer).
    session.chosen_path = "early_resolution"

    # Turn 2: sufficient_data → defence_theory → package.
    turn2 = await _drive(graph, session, "let's do early resolution")
    assert [n for n, _ in turn2] == ["sufficient_data", "defence_theory"]
    pkg = session.finalized_package()
    assert pkg is not None and pkg.kind == "early_resolution"


async def test_streaming_order_and_texts():
    graph = build_lawyer_graph(_agents(), MemorySaver())
    session = SessionState(session_id="s2", mode="lawyer")
    turn1 = await _drive(graph, session, "hi")
    texts = [t for _, t in turn1]
    assert texts[0].startswith("Tell me")
    assert texts[-1].startswith("You can pursue")
    # Assistant turns were recorded in transcript in order.
    assistant_turns = [t for t in session.transcript if t.role == "assistant"]
    assert len(assistant_turns) == 3


async def test_incomplete_intake_waits_for_next_turn():
    graph = build_lawyer_graph(_agents(complete=False), MemorySaver())
    session = SessionState(session_id="s3", mode="lawyer")
    turn = await _drive(graph, session, "uh I'm not sure")
    assert [n for n, _ in turn] == ["required_info"]  # stops, waits
    assert session.diagnosis is None


async def test_sufficient_false_routes_through_disclosure():
    graph = build_lawyer_graph(_agents(sufficient=False), MemorySaver())
    session = SessionState(session_id="s4", mode="lawyer")
    await _drive(graph, session, "ticket info")
    session.chosen_path = "early_resolution"
    turn2 = await _drive(graph, session, "early resolution")
    assert [n for n, _ in turn2] == ["sufficient_data", "disclosure", "defence_theory"]
    assert session.disclosure_requested is True
    assert session.er_package.is_preliminary is True  # preliminary after disclosure


async def test_pay_path_ends_with_no_package():
    graph = build_lawyer_graph(_agents(), MemorySaver())
    session = SessionState(session_id="s5", mode="lawyer")
    await _drive(graph, session, "ticket info")
    session.chosen_path = "pay"
    turn2 = await _drive(graph, session, "I'll just pay")
    assert turn2 == []  # graph routes straight to END
    assert session.finalized_package() is None


async def test_resumability_from_reloaded_state():
    """Kill mid-flow, rebuild a fresh graph, continue from persisted state."""
    graph1 = build_lawyer_graph(_agents(), MemorySaver())
    session = SessionState(session_id="s6", mode="lawyer")
    await _drive(graph1, session, "I got a ticket")  # advances to procedure_map

    # Simulate restart: serialize + reload the state, build a brand-new graph
    # with its own (empty) checkpointer.
    reloaded = SessionState.model_validate_json(session.model_dump_json())
    reloaded.chosen_path = "trial"
    graph2 = build_lawyer_graph(_agents(), MemorySaver())

    turn = await _drive(graph2, reloaded, "let's go to trial")
    # State-derived routing resumes at sufficient_data, no replay of earlier nodes.
    assert [n for n, _ in turn] == ["sufficient_data", "defence_theory"]
    assert reloaded.finalized_package() is not None
