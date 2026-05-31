"""WebSocket endpoints — text channel now, voice in Phase 9.

Implements IMPLEMENTATION_PLAN.md Phase 8. The handler is thin: it loads the
session, drives the orchestrator graph one turn at a time via ``astream_turn``,
and streams each node's assistant text back as ``agent_text`` envelopes. All
logic lives in the orchestrator — the handler only marshals messages.

Concurrency safety: the per-session lock is held across load → graph → save, so
two connections to the same session serialize and never corrupt state. A
mid-turn disconnect simply skips the save, leaving the store at the last
completed turn (reconnect resumes from there via state-derived routing).
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.memory.session import get_session_manager
from app.config import settings
from app.orchestrator.graph_judge import (
    astream_court_turn,
    build_judge_graph,
    get_judge_characters,
    get_judge_graph,
)
from app.orchestrator.graph_lawyer import (
    astream_turn,
    build_lawyer_graph,
    get_lawyer_agents,
    get_lawyer_graph,
)
from app.orchestrator.state import SessionState
from app.rag.results import RetrievalResult
from app.schemas.messages import (
    ErrorPayload,
    StateUpdatePayload,
    TextPayload,
    WSMessage,
)
from app.voice.asr import get_asr_client
from app.voice.audio2face import get_a2f_client
from app.voice.pipeline import VoiceSession, run_voice_turn
from app.voice.tts import get_tts_client

log = structlog.get_logger(__name__)

router = APIRouter()

WS_SESSION_NOT_FOUND = 4404

PATH_ALIASES = {
    "pay": ("pay", "just pay", "i'll pay"),
    "early_resolution": ("early resolution", "early_resolution", "resolution meeting"),
    "screening_review": ("screening review", "screening_review", "review"),
    "trial": ("trial", "mock trial", "go to trial"),
}


class EmptyRetriever:
    async def aretrieve(self, query: str, *args, **kwargs) -> RetrievalResult:
        return RetrievalResult(query=query, passages=[], scores=[], source="none")


def _fast_lawyer_graph():
    from langgraph.checkpoint.memory import MemorySaver

    from app.llm import get_chat_llm

    llm = get_chat_llm(temperature=0)
    return build_lawyer_graph(get_lawyer_agents(llm=llm, retriever=EmptyRetriever()), MemorySaver())


def _fast_judge_graph():
    from langgraph.checkpoint.memory import MemorySaver

    from app.llm import get_chat_llm

    llm = get_chat_llm(temperature=0.3)
    return build_judge_graph(get_judge_characters(llm=llm, retriever=EmptyRetriever()), MemorySaver())


def _get_lawyer_graph(app):
    """Lazily build + cache the lawyer graph on app.state (tests inject a fake)."""
    graph = getattr(app.state, "lawyer_graph", None)
    if graph is None:
        graph = _fast_lawyer_graph() if settings.graph_runtime == "fast_ai" else get_lawyer_graph()
        app.state.lawyer_graph = graph
    return graph


def _get_judge_graph(app):
    """Lazily build + cache the judge graph on app.state (tests inject a fake)."""
    graph = getattr(app.state, "judge_graph", None)
    if graph is None:
        graph = _fast_judge_graph() if settings.graph_runtime == "fast_ai" else get_judge_graph()
        app.state.judge_graph = graph
    return graph


def _extract_text(raw) -> str | None:
    """Accept either the full WSMessage envelope or a bare {text:...}."""
    if not isinstance(raw, dict):
        return None
    payload = raw.get("payload")
    if isinstance(payload, dict) and payload.get("text"):
        return payload["text"]
    return raw.get("text")


async def _send(ws: WebSocket, type_: str, session_id: str, payload, seq: int) -> None:
    msg = WSMessage.make(type_, session_id, payload, seq=seq)
    await ws.send_json(msg.model_dump(mode="json"))


@router.websocket("/ws/text/{session_id}")
async def text_channel(websocket: WebSocket, session_id: str) -> None:
    structlog.contextvars.bind_contextvars(session_id=session_id)
    await websocket.accept()
    mgr = await get_session_manager()

    state = await mgr.load(session_id)
    if state is None:
        await _send(
            websocket, "error", session_id,
            ErrorPayload(code="session_not_found", message="unknown session"), 0,
        )
        await websocket.close(code=WS_SESSION_NOT_FOUND)
        return

    if state.mode == "judge":
        graph = _get_judge_graph(websocket.app)
        driver = astream_court_turn
    else:
        graph = _get_lawyer_graph(websocket.app)
        driver = astream_turn

    seq = 0
    log.info("ws.connect", session_id=session_id, mode=state.mode)

    # Judge Mode opens itself: stream the call-to-order beats before any input.
    if state.mode == "judge":
        seq = await _run_turn(websocket, mgr, graph, driver, session_id, None, seq)

    try:
        while True:
            raw = await websocket.receive_json()
            user_text = _extract_text(raw)
            if not user_text:
                seq += 1
                await _send(
                    websocket, "error", session_id,
                    ErrorPayload(code="empty_message", message="no text in message"), seq,
                )
                continue

            seq = await _run_turn(websocket, mgr, graph, driver, session_id, user_text, seq)

    except WebSocketDisconnect:
        log.info("ws.disconnect", session_id=session_id)


async def _run_turn(
    websocket: WebSocket,
    mgr,
    graph,
    driver,
    session_id: str,
    user_text: str | None,
    seq: int,
) -> int:
    """One locked turn: reload → stream nodes → save → state_update.

    ``driver`` is the mode's turn generator (``astream_turn`` /
    ``astream_court_turn``); ``user_text=None`` drives a system-initiated turn
    (Judge Mode's opening).
    """
    async with mgr.lock(session_id):
        # Reload inside the lock so we act on the latest persisted state.
        state: SessionState | None = await mgr.load(session_id)
        if state is None:
            return seq
        if user_text is not None:
            _apply_lawyer_path_choice(state, user_text)

        agen = driver(graph, state) if user_text is None else driver(graph, state, user_text)
        async for node, text, state in agen:
            if text:
                seq += 1
                await _send(
                    websocket, "agent_text", session_id,
                    TextPayload(text=text, agent=node), seq,
                )

        await mgr.save(state)

    seq += 1
    await _send(websocket, "state_update", session_id, _state_summary(state), seq)
    return seq


def _apply_lawyer_path_choice(state: SessionState, user_text: str) -> None:
    """Promote a user path choice into graph state before routing resumes.

    Lawyer Mode intentionally pauses after procedure_map until chosen_path is
    set. The frontend sends natural text, so this small adapter maps obvious
    path choices onto the structured state field.
    """
    if state.mode != "lawyer" or state.chosen_path is not None:
        return
    if state.current_agent != "procedure_map" and state.diagnosis is None:
        return

    normalized = user_text.strip().lower().replace("-", " ")
    for path, aliases in PATH_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            state.chosen_path = path  # type: ignore[assignment]
            state.touch()
            return


def _state_summary(state: SessionState) -> StateUpdatePayload:
    summary = f"{len(state.transcript)} turns; agent={state.current_agent}"
    if state.mode == "judge" and state.court_phase is not None:
        summary += f"; phase={state.court_phase.value}"
    return StateUpdatePayload(
        current_agent=state.current_agent,
        chosen_path=state.chosen_path,
        summary=summary,
        flags=state.flags,
    )


# --- Voice channels (Phase 9) ---------------------------------------------


@router.websocket("/ws/voice/out/{session_id}")
async def voice_out(websocket: WebSocket, session_id: str) -> None:
    """Outbound: drains the session's queue (tts_audio + a2f_blendshapes) to the browser."""
    structlog.contextvars.bind_contextvars(session_id=session_id)
    await websocket.accept()
    mgr = await get_session_manager()
    if await mgr.load(session_id) is None:
        await websocket.close(code=WS_SESSION_NOT_FOUND)
        return

    voice = VoiceSession.get(session_id)
    log.info("ws.voice_out_connect", session_id=session_id)
    try:
        while True:
            message = await voice.outbound.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        log.info("ws.voice_out_disconnect", session_id=session_id)


@router.websocket("/ws/voice/in/{session_id}")
async def voice_in(websocket: WebSocket, session_id: str) -> None:
    """Inbound: browser audio → ASR → (on final) orchestrator turn → outbound queue.

    Interim transcripts during avatar speech trigger a barge-in cancel.
    """
    structlog.contextvars.bind_contextvars(session_id=session_id)
    await websocket.accept()
    mgr = await get_session_manager()
    state0 = await mgr.load(session_id)
    if state0 is None:
        await _send(websocket, "error", session_id,
                    ErrorPayload(code="session_not_found", message="unknown session"), 0)
        await websocket.close(code=WS_SESSION_NOT_FOUND)
        return

    voice = VoiceSession.get(session_id)
    asr, tts, a2f = get_asr_client(), get_tts_client(), get_a2f_client()
    if state0.mode == "judge":
        graph, driver = _get_judge_graph(websocket.app), astream_court_turn
    else:
        graph, driver = _get_lawyer_graph(websocket.app), astream_turn

    frames: asyncio.Queue = asyncio.Queue()

    async def frame_iter():
        while True:
            f = await frames.get()
            if f is None:  # close sentinel
                return
            yield f

    async def consume_asr():
        seq = 0
        async for tr in asr.transcribe_stream(frame_iter()):
            seq += 1
            kind = "asr_final" if tr.is_final else "asr_interim"
            await _send(websocket, kind, session_id, tr, seq)
            if not tr.is_final:
                voice.cancel_inflight()  # barge-in: stop the avatar
            else:
                voice.cancel_inflight()
                state = await mgr.load(session_id) or state0
                voice.current_task = asyncio.create_task(
                    _voice_turn(voice, mgr, state, tr.transcript, driver, graph, tts, a2f)
                )

    asr_task = asyncio.create_task(consume_asr())
    log.info("ws.voice_in_connect", session_id=session_id, mode=state0.mode)
    try:
        while True:
            data = await websocket.receive()
            if data.get("type") == "websocket.disconnect":
                break
            if data.get("bytes") is not None:
                await frames.put(data["bytes"])
            elif data.get("text") is not None:
                await frames.put(data["text"].encode())
    finally:
        await frames.put(None)
        asr_task.cancel()
        voice.cancel_inflight()
        log.info("ws.voice_in_disconnect", session_id=session_id)


async def _voice_turn(voice, mgr, state, user_text, driver, graph, tts, a2f) -> None:
    """Run + persist one voice turn, then emit a state_update. Cancellable (barge-in)."""
    try:
        async with mgr.lock(state.session_id):
            new_state = await run_voice_turn(voice, state, user_text, driver, graph, tts, a2f)
            await mgr.save(new_state)
        await voice.emit(
            WSMessage.make("state_update", state.session_id, _state_summary(new_state))
        )
    except asyncio.CancelledError:
        log.info("voice.turn_cancelled", session_id=state.session_id)
        raise
