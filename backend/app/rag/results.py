"""Shared RAG result models (ARCHITECTURE.md section 8)."""

from __future__ import annotations

from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field

RetrievalSource = Literal["rag", "tavily", "none"]


class Passage(BaseModel):
    """A single retrieved passage, from Chroma or Tavily."""

    content: str
    source_path: str | None = None  # corpus rel path, or URL for Tavily
    filename: str | None = None
    score: float | None = None
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def from_document(cls, doc: Document, score: float | None = None) -> "Passage":
        meta = dict(doc.metadata or {})
        return cls(
            content=doc.page_content,
            source_path=meta.get("source_path"),
            filename=meta.get("filename"),
            score=score if score is not None else meta.get("relevance_score"),
            metadata=meta,
        )


class RetrievalResult(BaseModel):
    """What ``ProsecutoRetriever.retrieve`` returns."""

    query: str
    passages: list[Passage] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    source: RetrievalSource = "none"

    @property
    def texts(self) -> list[str]:
        return [p.content for p in self.passages]
