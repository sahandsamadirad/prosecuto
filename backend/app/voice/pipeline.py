"""Voice pipeline — wires ASR → orchestrator → TTS → A2F (ARCHITECTURE §10).

``render_speech`` turns one assistant utterance into an interleaved stream of
``tts_audio`` + ``a2f_blendshapes`` envelopes (first-sentence kickoff: audio for
sentence 1 starts flowing before later sentences are synthesized).

``VoiceSession`` correlates the two per-session WebSocket channels (inbound audio
vs outbound audio+blendshapes) through an outbound queue, and holds the in-flight
turn task so a barge-in (new speech while the avatar is talking) can cancel it via
``asyncio.CancelledError``.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import structlog

from app.orchestrator.state import SessionState
from app.schemas.messages import TTSAudioPayload, WSMessage
from app.voice.audio2face import A2FClient
from app.voice.segment import iter_sentences
from app.voice.tts import VOICE_BY_AGENT, TTSClient

log = structlog.get_logger(__name__)


async def render_speech(
    text: str,
    session_id: str,
    tts: TTSClient,
    a2f: A2FClient,
    agent: str | None = None,
    start_seq: int = 0,
) -> AsyncIterator[WSMessage]:
    """Yield interleaved tts_audio + a2f_blendshapes envelopes for one utterance."""
    voice = VOICE_BY_AGENT.get(agent or "")
    seq = start_seq
    frame = 0
    for si, sentence in enumerate(iter_sentences(text)):
        async for chunk in tts.synthesize_stream(sentence, sentence_index=si, voice=voice):
            seq += 1
            yield WSMessage.make(
                "tts_audio",
                session_id,
                TTSAudioPayload(
                    audio_b64="",  # mock: bytes are silent; real client fills this
                    sample_rate=chunk.sample_rate,
                    sentence_index=si,
                ),
                seq=seq,
            )
            blend = await a2f.animate_chunk(chunk, frame)
            frame += 1
            seq += 1
            yield WSMessage.make("a2f_blendshapes", session_id, blend, seq=seq)


class VoiceSession:
    """Per-session voice state shared by the inbound and outbound WS channels."""

    _registry: dict[str, "VoiceSession"] = {}

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.outbound: asyncio.Queue[dict] = asyncio.Queue()
        self.current_task: asyncio.Task | None = None

    @classmethod
    def get(cls, session_id: str) -> "VoiceSession":
        vs = cls._registry.get(session_id)
        if vs is None:
            vs = cls(session_id)
            cls._registry[session_id] = vs
        return vs

    @classmethod
    def drop(cls, session_id: str) -> None:
        cls._registry.pop(session_id, None)

    async def emit(self, message: WSMessage) -> None:
        await self.outbound.put(message.model_dump(mode="json"))

    def cancel_inflight(self) -> None:
        """Barge-in: cancel the in-flight turn so the avatar stops speaking."""
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            log.info("voice.barge_in_cancel", session_id=self.session_id)


async def run_voice_turn(
    voice: VoiceSession,
    state: SessionState,
    user_text: str,
    drive,
    graph,
    tts: TTSClient,
    a2f: A2FClient,
) -> SessionState:
    """Run one orchestrator turn and stream its speech to the outbound queue.

    Cancellable: if cancelled mid-turn (barge-in), the partial audio simply stops
    and the exception propagates so the caller can drop the unsaved state.
    """
    seq = 0
    async for node, text, state in drive(graph, state, user_text):
        if not text:
            continue
        # Surface the agent text first (frontend can show captions immediately).
        seq += 1
        await voice.emit(WSMessage.make("agent_text", voice.session_id, {"text": text, "agent": node}, seq=seq))
        async for msg in render_speech(text, voice.session_id, tts, a2f, agent=node, start_seq=seq):
            seq = msg.seq
            await voice.emit(msg)
    return state
