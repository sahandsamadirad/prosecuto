"""Audio2Face-3D client — audio in, ARKit blendshapes out (real) / mock (dev).

ARCHITECTURE.md section 10: takes audio chunks, emits blendshape values at ~30fps
alongside the audio. The mock derives a simple oscillating ``jawOpen``/``mouthClose``
pose per audio chunk so the frontend has something to animate; the real A2F NIM
gRPC/WebSocket client drops in behind ``A2FClient``.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod

import structlog

from app.schemas.messages import BlendshapePayload
from app.voice.types import AudioChunk

log = structlog.get_logger(__name__)


class A2FClient(ABC):
    @abstractmethod
    async def animate_chunk(self, chunk: AudioChunk, frame_index: int) -> BlendshapePayload: ...


class MockA2FClient(A2FClient):
    """One blendshape frame per audio chunk, with an oscillating mouth pose."""

    async def animate_chunk(self, chunk: AudioChunk, frame_index: int) -> BlendshapePayload:
        jaw = 0.2 + 0.6 * (frame_index % 3) / 2.0  # 0.2 → 0.8 → 0.5 cycle
        return BlendshapePayload(
            values={"jawOpen": round(jaw, 3), "mouthClose": round(1.0 - jaw, 3)},
            frame_index=frame_index,
            audio_b64=base64.b64encode(chunk.audio).decode("ascii"),
        )


def get_a2f_client() -> A2FClient:
    """Return the configured A2F client (mock until the A2F NIM is wired up)."""
    # TODO(phase-11): return an Audio2Face3DClient when A2F_ENDPOINT is live.
    return MockA2FClient()
