"""Sentence segmentation for first-sentence TTS kickoff (ARCHITECTURE §10)."""

from __future__ import annotations

import re

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?", re.UNICODE)


def iter_sentences(text: str) -> list[str]:
    """Split text into trimmed sentences, splitting on . ! ? and newlines."""
    return [m.group().strip() for m in _SENTENCE.finditer(text) if m.group().strip()]
