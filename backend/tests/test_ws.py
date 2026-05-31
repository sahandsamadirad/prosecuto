"""Phase 8 tests: the WebSocket text channel.

A fake lawyer graph (deterministic agents) is injected on app.state so the test
exercises the WS handler + envelope + locking, not the LLM. Covers Phase 8
"done when": streamed turns, missing-session close, two independent sessions,
and reconnect-resumes-from-saved-state.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.agents.base import AgentResult
from app.main import app
from app.orchestrator.graph_lawyer import LawyerAgents, build_lawyer_graph
from app.orchestrator.state import SessionState
from app.schemas.case import TicketDetails, TicketDiagnosis
from app.schemas.packages import ERPackage


# --- Fake graph (mirrors the Phase 6 fakes) -------------------------------


class FakeAgent:
    def __init__(self, name, mutate, text):
        self.name, self._mutate, self._text = name, mutate, text

    async def run(self, state: SessionState) -> AgentResult:
        self._mutate(state)
        state.current_agent = self.name
        state.touch()
        return AgentResult(updated_state=state, assistant_text=self._text)


def _complete():
    return TicketDetails(
        ticket_type="camera_issued", ticket_date=date(2025, 11, 18), intersection="King & Bay",
        vehicle_owner="self", who_was_driving="self", ticket_number="RLC1",
        fine_amount=325.0, deadline_date=date(2026, 1, 1),
    )


def _fake_graph():
    agents = LawyerAgents(
        required_info=FakeAgent("required_info", lambda s: setattr(s, "ticket_details", _complete()), "Tell me more."),
        ticket_diagnosis=FakeAgent("ticket_diagnosis", lambda s: setattr(s, "diagnosis", TicketDiagnosis(
            type="camera_issued", sub_type="amps_camera", is_red_light_camera=True, recap_text="camera")), "It's a camera ticket."),
        procedure_map=FakeAgent("procedure_map", lambda s: None, "Pick a path."),
        sufficient_data=FakeAgent("sufficient_data", lambda s: setattr(s, "sufficient_data", True), "Checking."),
        disclosure=FakeAgent("disclosure", lambda s: None, "Disclosure."),
        defence_theory=FakeAgent("defence_theory", lambda s: setattr(s, "er_package", ERPackage(summary="plan")), "Here's your package."),
    )
    from langgraph.checkpoint.memory import MemorySaver

    return build_lawyer_graph(agents, MemorySaver())


def _client_with_fake_graph() -> TestClient:
    app.state.lawyer_graph = _fake_graph()
    return TestClient(app)


def _new_session(client, mode="lawyer") -> str:
    return client.post("/api/session", json={"mode": mode}).json()["session_id"]


# --- Tests ----------------------------------------------------------------


def test_ws_streams_agent_text_and_state_update():
    client = _client_with_fake_graph()
    sid = _new_session(client)
    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        ws.send_json({"type": "user_text", "payload": {"text": "I got a red light camera ticket"}})
        types = []
        while True:
            msg = ws.receive_json()
            types.append(msg["type"])
            assert msg["session_id"] == sid
            if msg["type"] == "state_update":
                break
    # Intake completes → diagnosis → procedure_map, then a state_update.
    assert types == ["agent_text", "agent_text", "agent_text", "state_update"]


def test_ws_unknown_session_closes_4404():
    from starlette.websockets import WebSocketDisconnect

    client = _client_with_fake_graph()
    with client.websocket_connect("/ws/text/nope") as ws:
        first = ws.receive_json()
        assert first["type"] == "error"
        try:
            ws.receive_json()  # server closes after the error
            raise AssertionError("expected disconnect")
        except WebSocketDisconnect as exc:
            assert exc.code == 4404


def test_ws_empty_message_returns_error_but_stays_open():
    client = _client_with_fake_graph()
    sid = _new_session(client)
    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        ws.send_json({"type": "user_text", "payload": {"text": ""}})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["payload"]["code"] == "empty_message"


def test_two_sessions_are_independent():
    client = _client_with_fake_graph()
    s1, s2 = _new_session(client), _new_session(client)
    with client.websocket_connect(f"/ws/text/{s1}") as ws1, \
         client.websocket_connect(f"/ws/text/{s2}") as ws2:
        ws1.send_json({"text": "ticket one"})
        ws2.send_json({"text": "ticket two"})
        # Drain both to state_update; sessions don't cross wires.
        for ws, sid in ((ws1, s1), (ws2, s2)):
            while True:
                m = ws.receive_json()
                assert m["session_id"] == sid
                if m["type"] == "state_update":
                    break
    # Both persisted independently.
    assert client.get(f"/api/session/{s1}").json()["diagnosis"] is not None
    assert client.get(f"/api/session/{s2}").json()["diagnosis"] is not None


def test_judge_mode_ws_opens_automatically_and_streams_beats():
    from app.agents.base import AgentResult
    from app.orchestrator.graph_judge import JudgeCharacters, build_judge_graph
    from langgraph.checkpoint.memory import MemorySaver

    class FakeChar:
        def __init__(self, name):
            self.name = name

        async def run(self, state):
            return AgentResult(updated_state=state, assistant_text=f"{self.name}@{state.court_phase.value}")

    app.state.judge_graph = build_judge_graph(
        JudgeCharacters(FakeChar("court_clerk"), FakeChar("judge"), FakeChar("crown_prosecutor")),
        MemorySaver(),
    )
    client = TestClient(app)
    sid = client.post("/api/session", json={"mode": "judge"}).json()["session_id"]

    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        # Opening beats stream automatically on connect (no input needed).
        agents = []
        while True:
            m = ws.receive_json()
            if m["type"] == "agent_text":
                agents.append(m["payload"]["agent"])
            if m["type"] == "state_update":
                break
        assert agents == ["court_clerk", "court_clerk", "judge", "crown_prosecutor"]
        assert "phase=defence_opening" in m["payload"]["summary"]


def test_reconnect_resumes_from_saved_state():
    client = _client_with_fake_graph()
    sid = _new_session(client)

    # Turn 1: complete intake → diagnosis → procedure_map (waits for choice).
    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        ws.send_json({"text": "I got a ticket"})
        while ws.receive_json()["type"] != "state_update":
            pass

    # User picks a path out-of-band, then reconnects.
    st = client.get(f"/api/session/{sid}").json()
    assert st["diagnosis"] is not None and st["chosen_path"] is None
    # Set chosen_path via a fresh load/save through the API-less manager path:
    import asyncio

    from app.memory.session import get_session_manager

    async def choose():
        mgr = await get_session_manager()
        s = await mgr.load(sid)
        s.chosen_path = "early_resolution"
        await mgr.save(s)

    asyncio.run(choose())

    # Turn 2 on reconnect: resumes at sufficient_data → defence_theory.
    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        ws.send_json({"text": "early resolution"})
        agent_msgs = []
        while True:
            m = ws.receive_json()
            if m["type"] == "agent_text":
                agent_msgs.append(m["payload"]["agent"])
            if m["type"] == "state_update":
                break
    assert agent_msgs == ["sufficient_data", "defence_theory"]
    assert client.get(f"/api/session/{sid}/package").json()["kind"] == "early_resolution"


def test_explicit_package_request_forces_final_package_from_intake():
    client = _client_with_fake_graph()
    sid = _new_session(client)

    with client.websocket_connect(f"/ws/text/{sid}") as ws:
        ws.send_json({"text": "Let's go with early resolution - please prepare my defence package."})
        agent_msgs = []
        while True:
            m = ws.receive_json()
            if m["type"] == "agent_text":
                agent_msgs.append(m["payload"]["agent"])
            if m["type"] == "state_update":
                break

    assert agent_msgs == ["defence_theory"]
    package = client.get(f"/api/session/{sid}/package").json()
    assert package["kind"] == "early_resolution"
