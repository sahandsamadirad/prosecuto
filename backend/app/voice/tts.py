"""TTS client — Riva/Magpie streaming (real) / a deterministic mock (dev).

ARCHITECTURE.md section 10: sentence-by-sentence streaming so the avatar starts
speaking on the first sentence. The mock emits deterministic PCM-shaped bytes in
chunks proportional to the text length; the real client drops in behind
``TTSClient``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

import structlog

from app.voice.types import AudioChunk

log = structlog.get_logger(__name__)

_CHARS_PER_CHUNK = 20  # mock pacing


class TTSClient(ABC):
    sample_rate: int = 22050

    @abstractmethod
    def synthesize_stream(
        self, text: str, sentence_index: int = 0, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]: ...


class MockTTSClient(TTSClient):
    """Emits fixed-size silent PCM chunks sized to the text (no real audio)."""

    async def synthesize_stream(
        self, text: str, sentence_index: int = 0, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        n_chunks = max(1, len(text) // _CHARS_PER_CHUNK)
        for i in range(n_chunks):
            # 512 bytes of 16-bit silence stands in for a real audio frame.
            yield AudioChunk(
                audio=bytes(512),
                sample_rate=self.sample_rate,
                index=i,
                sentence_index=sentence_index,
            )


# Per-character voices for Judge Mode (each character gets a distinct voice id).
VOICE_BY_AGENT = {
    "judge": "English-US.Male-Calm",
    "crown_prosecutor": "English-US.Female-Neutral",
    "court_clerk": "English-US.Male-Neutral",
}


def get_tts_client() -> TTSClient:
    """Return the configured TTS client (mock until Riva/Magpie is wired up)."""
    # TODO(phase-11): return a RivaTTSClient when RIVA_TTS_ENDPOINT is live.
    return MockTTSClient()
