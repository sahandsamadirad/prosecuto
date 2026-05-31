"""Phase 9 tests: voice pipeline (mock clients + streaming plumbing).

All offline. Covers the mock ASR/TTS/A2F clients, sentence segmentation, the
interleaved render_speech stream, run_voice_turn emitting to the outbound queue,
barge-in cancellation, and a dual-channel (in/out) WebSocket integration.
"""

from __future__ import annotations

import asyncio
from datetime import date

from fastapi.testclient import TestClient

from app.agents.base import AgentResult
from app.main import app
from app.orchestrator.graph_lawyer import LawyerAgents, astream_turn, build_lawyer_graph
from app.orchestrator.state import SessionState
from app.schemas.case import TicketDetails, TicketDiagnosis
from app.voice.asr import END_OF_UTTERANCE, MockASRClient
from app.voice.audio2face import MockA2FClient
from app.voice.pipeline import VoiceSession, render_speech, run_voice_turn
from app.voice.segment import iter_sentences
from app.voice.tts import MockTTSClient
from app.voice.types import AudioChunk


async def _frames(*items):
    for it in items:
        yield it


def _fake_lawyer_graph():
    from langgraph.checkpoint.memory import MemorySaver

    def complete():
        return TicketDetails(
            ticket_type="camera_issued", ticket_date=date(2025, 11, 18), intersection="King & Bay",
            vehicle_owner="self", who_was_driving="self", ticket_number="RLC1",
            fine_amount=325.0, deadline_date=date(2026, 1, 1),
        )

    class FakeAgent:
        def __init__(self, name, mutate, text):
            self.name, self._m, self._t = name, mutate, text

        async def run(self, s):
            self._m(s)
            s.current_agent = self.name
            s.touch()
            return AgentResult(updated_state=s, assistant_text=self._t)

    agents = LawyerAgents(
        required_info=FakeAgent("required_info", lambda s: setattr(s, "ticket_details", complete()), "Tell me more about it."),
        ticket_diagnosis=FakeAgent("ticket_diagnosis", lambda s: setattr(s, "diagnosis", TicketDiagnosis(
            type="camera_issued", sub_type="amps_camera", is_red_light_camera=True, recap_text="x")), "This is a camera ticket. Got it."),
        procedure_map=FakeAgent("procedure_map", lambda s: None, "You can try early resolution. Or a trial."),
        sufficient_data=FakeAgent("sufficient_data", lambda s: setattr(s, "sufficient_data", True), "Checking."),
        disclosure=FakeAgent("disclosure", lambda s: None, "Disclosure."),
        defence_theory=FakeAgent("defence_theory", lambda s: None, "Package."),
    )
    return build_lawyer_graph(agents, MemorySaver())


# --- Mock clients ---------------------------------------------------------


async def test_mock_asr_emits_interim_then_final():
    asr = MockASRClient()
    out = [t async for t in asr.transcribe_stream(_frames(b"hello ", b"world", END_OF_UTTERANCE))]
    assert any(not t.is_final for t in out)  # interims
    assert out[-1].is_final and out[-1].transcript == "hello world"


async def test_mock_asr_finalizes_on_stream_close():
    asr = MockASRClient()
    out = [t async for t in asr.transcribe_stream(_frames(b"just one"))]
    assert out[-1].is_final and out[-1].transcript == "just one"


async def test_mock_tts_streams_chunks():
    chunks = [c async for c in MockTTSClient().synthesize_stream("Hello there, friend of mine.", 0)]
    assert len(chunks) >= 1
    assert all(c.sample_rate == 22050 for c in chunks)


async def test_mock_a2f_emits_blendshapes_with_audio():
    bp = await MockA2FClient().animate_chunk(AudioChunk(audio=bytes(512)), 0)
    assert "jawOpen" in bp.values and "mouthClose" in bp.values
    assert bp.audio_b64


def test_iter_sentences():
    assert iter_sentences("Hello. How are you? I am fine!") == ["Hello.", "How are you?", "I am fine!"]


# --- render_speech --------------------------------------------------------


async def test_render_speech_interleaves_audio_and_blendshapes():
    msgs = [m async for m in render_speech("Hello there. Goodbye now.", "sid", MockTTSClient(), MockA2FClient(), agent="judge")]
    types = [m.type for m in msgs]
    assert "tts_audio" in types and "a2f_blendshapes" in types
    assert types.count("tts_audio") == types.count("a2f_blendshapes")  # one blendshape per chunk
    assert [m.seq for m in msgs] == sorted(m.seq for m in msgs)  # monotonic seq


# --- run_voice_turn -------------------------------------------------------


async def test_run_voice_turn_emits_agent_text_audio_and_blendshapes():
    voice = VoiceSession("vt1")
    state = SessionState(session_id="vt1", mode="lawyer")
    await run_voice_turn(voice, state, "I got a red light camera ticket",
                         astream_turn, _fake_lawyer_graph(), MockTTSClient(), MockA2FClient())
    seen = set()
    while not voice.outbound.empty():
        seen.add(voice.outbound.get_nowait()["type"])
    assert {"agent_text", "tts_audio", "a2f_blendshapes"} <= seen
    VoiceSession.drop("vt1")


# --- Barge-in / registry --------------------------------------------------


async def test_voice_session_registry_is_shared_and_droppable():
    vs = VoiceSession.get("shared")
    assert VoiceSession.get("shared") is vs
    VoiceSession.drop("shared")
    assert VoiceSession.get("shared") is not vs


async def test_cancel_inflight_stops_the_turn_task():
    vs = VoiceSession("cancel1")

    async def long_turn():
        await asyncio.sleep(5)

    vs.current_task = asyncio.create_task(long_turn())
    await asyncio.sleep(0)
    vs.cancel_inflight()
    try:
        await vs.current_task
    except asyncio.CancelledError:
        pass
    assert vs.current_task.cancelled()
    VoiceSession.drop("cancel1")


# --- WS endpoint integration ----------------------------------------------


def test_voice_in_channel_streams_transcripts():
    """Inbound socket: text frames → ASR interim + final back on the same socket."""
    app.state.lawyer_graph = _fake_lawyer_graph()
    client = TestClient(app)
    sid = client.post("/api/session", json={"mode": "lawyer"}).json()["session_id"]

    with client.websocket_connect(f"/ws/voice/in/{sid}") as in_ws:
        in_ws.send_text("I got a red light camera ticket")
        in_ws.send_bytes(END_OF_UTTERANCE)
        m1 = in_ws.receive_json()
        m2 = in_ws.receive_json()
        assert m1["type"] == "asr_interim"
        assert m2["type"] == "asr_final"
        assert m2["payload"]["transcript"] == "I got a red light camera ticket"
    VoiceSession.drop(sid)


def test_voice_channels_reject_unknown_session():
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app)
    for path in ("/ws/voice/out/nope", "/ws/voice/in/nope"):
        with client.websocket_connect(path) as ws:
            try:
                # in-channel sends an error first; out-channel closes immediately.
                ws.receive_json()
                ws.receive_json()
                raise AssertionError("expected disconnect")
            except WebSocketDisconnect as exc:
                assert exc.code == 4404
