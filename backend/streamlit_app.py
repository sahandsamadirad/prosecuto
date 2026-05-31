"""Streamlit test harness for Prosecuto graphs and AI agents.

Run from the backend directory:

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import streamlit as st
from langgraph.checkpoint.memory import MemorySaver

from app.agents.base import AgentResult
from app.config import settings
from app.orchestrator.graph_judge import (
    JudgeCharacters,
    astream_court_turn,
    build_judge_graph,
    get_judge_characters,
    get_judge_graph,
)
from app.orchestrator.graph_lawyer import (
    LawyerAgents,
    astream_turn,
    build_lawyer_graph,
    get_lawyer_agents,
    get_lawyer_graph,
)
from app.orchestrator.state import CourtPhase, SessionState
from app.rag.results import RetrievalResult
from app.schemas.case import TicketDetails, TicketDiagnosis
from app.schemas.packages import DisclosurePackage, ERPackage


class EmptyRetriever:
    async def aretrieve(self, query: str, *args, **kwargs) -> RetrievalResult:
        return RetrievalResult(query=query, passages=[], scores=[], source="none")


class FakeLawyerAgent:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text

    async def run(self, state: SessionState) -> AgentResult:
        if self.name == "required_info":
            state.ticket_details = TicketDetails(
                ticket_type="camera_issued",
                ticket_date=date(2025, 11, 18),
                intersection="King & Bay",
                municipality="Toronto",
                vehicle_owner="self",
                who_was_driving="self",
                ticket_number="RLC-TEST",
                fine_amount=325.0,
                deadline_date=date(2026, 1, 1),
            )
        elif self.name == "ticket_diagnosis":
            state.diagnosis = TicketDiagnosis(
                type="camera_issued",
                sub_type="amps_camera",
                is_red_light_camera=True,
                deadline_status="within_window",
                recap_text="Test camera ticket, inside the response window.",
            )
        elif self.name == "sufficient_data":
            state.sufficient_data = True
        elif self.name == "disclosure":
            state.disclosure_requested = True
            state.disclosure_package = DisclosurePackage(request_text="Please disclose the camera records.")
        elif self.name == "defence_theory":
            state.er_package = ERPackage(summary="Test early resolution package.")

        state.current_agent = self.name
        state.touch()
        return AgentResult(updated_state=state, assistant_text=self.text)


class FakeCourtCharacter:
    def __init__(self, name: str) -> None:
        self.name = name

    async def run(self, state: SessionState) -> AgentResult:
        phase = state.court_phase.value if state.court_phase else "idle"
        text = f"{self.name} speaking for phase: {phase}."
        return AgentResult(updated_state=state, assistant_text=text)


def run_async(coro):
    return asyncio.run(coro)


def new_lawyer_session() -> SessionState:
    return SessionState(session_id=str(uuid4()), mode="lawyer")


def new_judge_session() -> SessionState:
    return SessionState(
        session_id=str(uuid4()),
        mode="judge",
        court_phase=CourtPhase.IDLE,
        court_transcript=[],
    )


def fake_lawyer_graph():
    return build_lawyer_graph(
        LawyerAgents(
            required_info=FakeLawyerAgent("required_info", "I have the ticket details for this test case."),
            ticket_diagnosis=FakeLawyerAgent("ticket_diagnosis", "This looks like an AMPS camera ticket."),
            procedure_map=FakeLawyerAgent("procedure_map", "Choose pay, early resolution, screening review, or trial."),
            sufficient_data=FakeLawyerAgent("sufficient_data", "The test case has enough information."),
            disclosure=FakeLawyerAgent("disclosure", "A disclosure request has been prepared."),
            defence_theory=FakeLawyerAgent("defence_theory", "Here is a test package."),
        ),
        MemorySaver(),
    )


def fake_judge_graph():
    return build_judge_graph(
        JudgeCharacters(
            clerk=FakeCourtCharacter("court_clerk"),
            judge=FakeCourtCharacter("judge"),
            prosecutor=FakeCourtCharacter("crown_prosecutor"),
        ),
        MemorySaver(),
    )


def fast_lawyer_graph():
    from app.llm import get_chat_llm

    llm = get_chat_llm(temperature=0)
    return build_lawyer_graph(get_lawyer_agents(llm=llm, retriever=EmptyRetriever()), MemorySaver())


def fast_judge_graph():
    from app.llm import get_chat_llm

    llm = get_chat_llm(temperature=0.0)
    return build_judge_graph(get_judge_characters(llm=llm, retriever=EmptyRetriever()), MemorySaver())


def get_graph(mode: str, kind: str):
    key = f"{kind}_graph_{mode}"
    if key not in st.session_state:
        if kind == "lawyer":
            if mode == "Smoke test":
                st.session_state[key] = fake_lawyer_graph()
            elif mode == "Fast AI":
                st.session_state[key] = fast_lawyer_graph()
            else:
                st.session_state[key] = get_lawyer_graph()
        else:
            if mode == "Smoke test":
                st.session_state[key] = fake_judge_graph()
            elif mode == "Fast AI":
                st.session_state[key] = fast_judge_graph()
            else:
                st.session_state[key] = get_judge_graph()
    return st.session_state[key]


async def collect_lawyer_turn(graph, session: SessionState, user_message: str):
    events = []
    async for node, text, updated in astream_turn(graph, session, user_message):
        events.append((node, text))
        session = updated
    return events, session


async def collect_judge_turn(graph, session: SessionState, user_message: str | None):
    events = []
    async for speaker, text, updated in astream_court_turn(graph, session, user_message):
        events.append((speaker, text))
        session = updated
    return events, session


def render_transcript(session: SessionState, court: bool = False) -> None:
    turns = session.court_transcript if court else session.transcript
    if not turns:
        st.info("No transcript yet.")
        return

    for turn in turns:
        label = turn.agent or turn.role
        with st.chat_message("user" if turn.role == "user" else "assistant"):
            st.caption(label)
            st.write(turn.content)


def render_events(events: list[tuple[str, str]]) -> None:
    if not events:
        st.info("The graph reached a wait/end state without emitting text.")
        return
    for name, text in events:
        st.write(f"**{name}**")
        st.write(text)


st.set_page_config(page_title="Prosecuto Graph Lab", layout="wide")
st.title("Prosecuto Graph Lab")

with st.sidebar:
    graph_mode = st.radio("Graph backend", ["Smoke test", "Fast AI", "Real AI"])
    st.caption(f"NVIDIA API key: {'configured' if settings.nvidia_api_key else 'missing'}")
    st.caption(f"LLM: {settings.nim_llm_model}")
    st.caption(f"Chroma: {settings.chroma_persist_dir}")

    if graph_mode == "Smoke test":
        st.info("Fastest: deterministic fake agents, no AI calls.")
    elif graph_mode == "Fast AI":
        st.info("Uses the real LLM, but skips Chroma, embeddings, reranking, and RAG critics.")
    if graph_mode == "Real AI" and not settings.nvidia_api_key:
        st.warning("Set NVIDIA_API_KEY in backend/.env before using Real AI.")
    elif graph_mode == "Real AI":
        st.warning("Slowest: runs the full RAG pipeline and multiple LLM calls per turn.")

    if st.button("Reset lawyer session"):
        st.session_state.lawyer_session = new_lawyer_session()
    if st.button("Reset judge session"):
        st.session_state.judge_session = new_judge_session()

if "lawyer_session" not in st.session_state:
    st.session_state.lawyer_session = new_lawyer_session()
if "judge_session" not in st.session_state:
    st.session_state.judge_session = new_judge_session()

lawyer_tab, judge_tab, state_tab = st.tabs(["Lawyer graph", "Judge graph", "State"])

with lawyer_tab:
    session = st.session_state.lawyer_session
    left, right = st.columns([2, 1])

    with left:
        render_transcript(session)
        message = st.chat_input("Send a lawyer-mode test message", key="lawyer_input")

    with right:
        st.subheader("Controls")
        chosen = st.selectbox(
            "Chosen path",
            ["", "pay", "early_resolution", "screening_review", "trial"],
            index=0,
        )
        if chosen:
            session.chosen_path = chosen
        st.write("Current agent:", session.current_agent or "none")
        st.write("Chosen path:", session.chosen_path or "none")
        st.write("Package ready:", bool(session.finalized_package()))

    if message:
        try:
            graph = get_graph(graph_mode, "lawyer")
            with st.spinner("Running lawyer graph..."):
                events, updated = run_async(collect_lawyer_turn(graph, session, message))
            st.session_state.lawyer_session = updated
            render_events(events)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Lawyer graph failed: {exc}")

with judge_tab:
    session = st.session_state.judge_session
    left, right = st.columns([2, 1])

    with left:
        render_transcript(session, court=True)
        court_message = st.chat_input("Send defendant court speech", key="judge_input")

    with right:
        st.subheader("Controls")
        st.write("Court phase:", session.court_phase.value if session.court_phase else "none")
        run_opening = st.button("Run next court beats")

    if run_opening or court_message:
        try:
            graph = get_graph(graph_mode, "judge")
            with st.spinner("Running judge graph..."):
                events, updated = run_async(collect_judge_turn(graph, session, court_message))
            st.session_state.judge_session = updated
            render_events(events)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Judge graph failed: {exc}")

with state_tab:
    st.subheader("Lawyer state")
    st.json(st.session_state.lawyer_session.model_dump(mode="json"))
    st.subheader("Judge state")
    st.json(st.session_state.judge_session.model_dump(mode="json"))
