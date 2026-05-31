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

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.memory.session import get_session_manager
from app.orchestrator.graph_lawyer import astream_turn, get_lawyer_graph
from app.orchestrator.state import SessionState
from app.schemas.messages import (
    ErrorPayload,
    StateUpdatePayload,
    TextPayload,
    WSMessage,
)

log = structlog.get_logger(__name__)

router = APIRouter()

WS_SESSION_NOT_FOUND = 4404


def _get_lawyer_graph(app):
    """Lazily build + cache the lawyer graph on app.state (tests inject a fake)."""
    graph = getattr(app.state, "lawyer_graph", None)
    if graph is None:
        graph = get_lawyer_graph()
        app.state.lawyer_graph = graph
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

    if state.mode != "lawyer":
        await _send(
            websocket, "error", session_id,
            ErrorPayload(code="unsupported_mode", message="text channel is Lawyer Mode only"), 0,
        )
        await websocket.close(code=4400)
        return

    graph = _get_lawyer_graph(websocket.app)
    seq = 0
    log.info("ws.connect", session_id=session_id)

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

            seq = await _run_turn(websocket, mgr, graph, session_id, user_text, seq)

    except WebSocketDisconnect:
        log.info("ws.disconnect", session_id=session_id)


async def _run_turn(
    websocket: WebSocket,
    mgr,
    graph,
    session_id: str,
    user_text: str,
    seq: int,
) -> int:
    """One locked turn: reload → stream nodes → save → state_update."""
    async with mgr.lock(session_id):
        # Reload inside the lock so we act on the latest persisted state.
        state: SessionState = await mgr.load(session_id) or SessionState(
            session_id=session_id, mode="lawyer"
        )

        async for node, text, state in astream_turn(graph, state, user_text):
            if text:
                seq += 1
                await _send(
                    websocket, "agent_text", session_id,
                    TextPayload(text=text, agent=node), seq,
                )

        await mgr.save(state)

    seq += 1
    await _send(
        websocket, "state_update", session_id,
        StateUpdatePayload(
            current_agent=state.current_agent,
            chosen_path=state.chosen_path,
            summary=f"{len(state.transcript)} turns; agent={state.current_agent}",
            flags=state.flags,
        ),
        seq,
    )
    return seq
