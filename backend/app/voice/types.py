"""Shared voice-pipeline types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioChunk:
    """A chunk of synthesized PCM audio flowing TTS → A2F → browser."""

    audio: bytes
    sample_rate: int = 22050
    index: int = 0
    sentence_index: int = 0
