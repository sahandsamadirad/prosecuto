"""ASR client — Riva Parakeet streaming (real) / a text-frame mock (dev).

ARCHITECTURE.md section 10: streaming input, emits interim + final transcripts.
Real Riva/A2F hardware isn't wired yet, so per IMPLEMENTATION_PLAN's "mock first"
rule the default is a mock that treats incoming frames as UTF-8 text — it streams
interim transcripts as the buffer grows and a final on an ``__END__`` sentinel or
when the frame stream closes. The real gRPC client drops in behind ``ASRClient``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

import structlog

from app.schemas.messages import ASRPayload

log = structlog.get_logger(__name__)

END_OF_UTTERANCE = b"__END__"


class ASRClient(ABC):
    @abstractmethod
    def transcribe_stream(
        self, frames: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPayload]: ...


class MockASRClient(ASRClient):
    """Text-frame mock: each frame is appended; ``__END__`` flushes a final."""

    async def transcribe_stream(
        self, frames: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPayload]:
        buffer = ""
        async for frame in frames:
            if frame == END_OF_UTTERANCE:
                if buffer.strip():
                    yield ASRPayload(transcript=buffer.strip(), is_final=True, confidence=0.99)
                buffer = ""
                continue
            buffer += frame.decode("utf-8", errors="ignore")
            yield ASRPayload(transcript=buffer.strip(), is_final=False, confidence=0.5)
        if buffer.strip():
            yield ASRPayload(transcript=buffer.strip(), is_final=True, confidence=0.99)


def get_asr_client() -> ASRClient:
    """Return the configured ASR client (mock until Riva is wired up)."""
    # TODO(phase-11): return a RivaParakeetClient when RIVA_ASR_ENDPOINT is live.
    return MockASRClient()
