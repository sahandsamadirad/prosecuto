"""WebSocket message envelope and payloads (ARCHITECTURE §10).

Every WS frame — inbound audio, ASR transcripts, agent text, TTS audio,
blendshapes, state updates, errors — uses the same ``WSMessage`` envelope so the
thin WS handlers can marshal generically and the orchestrator owns the logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WSMessageType = Literal[
    "asr_interim",
    "asr_final",
    "user_text",      # text-channel user input
    "agent_text",     # streamed assistant text (→ TTS)
    "tts_audio",      # base64 audio chunk
    "a2f_blendshapes",
    "state_update",
    "error",
]


# --- Typed payloads -------------------------------------------------------


class ASRPayload(BaseModel):
    transcript: str
    is_final: bool = False
    confidence: float | None = None


class TextPayload(BaseModel):
    text: str
    agent: str | None = None  # which character is speaking


class TTSAudioPayload(BaseModel):
    audio_b64: str
    sample_rate: int = 22050
    sentence_index: int | None = None


class BlendshapePayload(BaseModel):
    # ARKit-compatible blendshape values at ~30fps.
    values: dict[str, float]
    frame_index: int | None = None
    audio_b64: str | None = None


class StateUpdatePayload(BaseModel):
    current_agent: str | None = None
    chosen_path: str | None = None
    summary: str | None = None
    flags: list[str] = Field(default_factory=list)


class ErrorPayload(BaseModel):
    code: str
    message: str


AnyPayload = (
    ASRPayload
    | TextPayload
    | TTSAudioPayload
    | BlendshapePayload
    | StateUpdatePayload
    | ErrorPayload
)


class WSMessage(BaseModel):
    """The universal WebSocket envelope."""

    type: WSMessageType
    session_id: str
    seq: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)
    # Kept as a dict on the wire for flexibility; construct via the helpers
    # below to validate against the typed payloads.
    payload: dict = Field(default_factory=dict)

    @classmethod
    def make(
        cls,
        type: WSMessageType,
        session_id: str,
        payload: BaseModel | dict,
        seq: int = 0,
    ) -> "WSMessage":
        data = payload.model_dump() if isinstance(payload, BaseModel) else payload
        return cls(type=type, session_id=session_id, seq=seq, payload=data)
