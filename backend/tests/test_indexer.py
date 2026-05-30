"""Phase 1 tests for the corpus indexer.

These run fully offline with a deterministic fake LangChain ``Embeddings``
injected into ``build_index`` so they're fast and don't touch the NVIDIA API.
They cover the IMPLEMENTATION_PLAN.md Phase 1 "done when" criteria:

* indexing a small file creates a Chroma collection and the right chunk is
  retrievable via the LangChain vectorstore;
* re-running is idempotent — the chunk count does not grow.
"""

from __future__ import annotations

import hashlib

import pytest
from langchain_core.embeddings import Embeddings

from app.rag.indexer import (
    IndexStats,
    _chunk_id,
    build_index,
    get_vectorstore,
)


class FakeEmbeddings(Embeddings):
    """Deterministic, offline LangChain embeddings.

    Maps text → a fixed-dim vector via a hash of its tokens. Identical text
    always embeds identically, so a query containing a chunk's distinctive
    terms retrieves that chunk — enough to prove the wiring.
    """

    DIM = 64

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.DIM] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "hta_s144.txt").write_text(
        "Red light offence. Every driver approaching a red light shall stop. "
        "Failure to stop at a red light is an offence under the Highway Traffic Act.\n\n"
        "A red light camera may record a vehicle that fails to stop.",
        encoding="utf-8",
    )
    nested = d / "nested"
    nested.mkdir()
    (nested / "disclosure.txt").write_text(
        "Stinchcombe disclosure. The Crown must disclose all relevant evidence "
        "to the defence before trial.",
        encoding="utf-8",
    )
    return d


def _count(chroma_dir, collection: str, embeddings) -> int:
    store = get_vectorstore(embeddings, str(chroma_dir), collection)
    return store._collection.count()


def test_index_creates_collection_and_chunks(corpus, tmp_path):
    chroma_dir = tmp_path / "chroma"
    emb = FakeEmbeddings()
    stats = build_index(
        corpus_dir=str(corpus),
        chroma_dir=str(chroma_dir),
        collection_name="test",
        chunk_size=120,
        chunk_overlap=20,
        embeddings=emb,
    )
    assert isinstance(stats, IndexStats)
    assert stats.files_processed == 2
    assert stats.chunks_created > 0
    assert stats.errors == []
    assert _count(chroma_dir, "test", emb) == stats.chunks_created


def test_recursive_discovery_finds_nested_files(corpus, tmp_path):
    stats = build_index(
        corpus_dir=str(corpus),
        chroma_dir=str(tmp_path / "chroma"),
        collection_name="test",
        embeddings=FakeEmbeddings(),
    )
    assert stats.files_processed == 2  # top-level + nested/, via rglob


def test_idempotent_reindex_does_not_duplicate(corpus, tmp_path):
    chroma_dir = tmp_path / "chroma"
    emb = FakeEmbeddings()
    kwargs = dict(
        corpus_dir=str(corpus),
        chroma_dir=str(chroma_dir),
        collection_name="test",
        chunk_size=120,
        chunk_overlap=20,
        embeddings=emb,
    )
    first = build_index(**kwargs)
    count_after_first = _count(chroma_dir, "test", emb)

    second = build_index(**kwargs)
    count_after_second = _count(chroma_dir, "test", emb)

    assert count_after_first == count_after_second
    assert first.chunks_created == second.chunks_created


def test_query_returns_relevant_chunk(corpus, tmp_path):
    chroma_dir = tmp_path / "chroma"
    emb = FakeEmbeddings()
    build_index(
        corpus_dir=str(corpus),
        chroma_dir=str(chroma_dir),
        collection_name="test",
        chunk_size=120,
        chunk_overlap=20,
        embeddings=emb,
    )
    store = get_vectorstore(emb, str(chroma_dir), "test")
    hits = store.similarity_search("Stinchcombe disclosure Crown evidence", k=1)
    assert hits
    top = hits[0]
    assert "Stinchcombe" in top.page_content or "disclose" in top.page_content
    assert top.metadata["filename"] == "disclosure.txt"
    # Metadata contract from ARCHITECTURE.md section 7.
    for key in (
        "source_path",
        "filename",
        "chunk_index",
        "char_start",
        "char_end",
        "total_chunks",
    ):
        assert key in top.metadata


def test_chunk_id_is_deterministic_and_unique():
    a = _chunk_id("hta_s144.txt", 0)
    b = _chunk_id("hta_s144.txt", 0)
    c = _chunk_id("hta_s144.txt", 1)
    assert a == b  # same input → same id (idempotent upsert)
    assert a != c  # different chunk index → different id
    assert len(a) == 64  # sha256 hexdigest


def test_missing_corpus_dir_returns_error_not_crash(tmp_path):
    stats = build_index(
        corpus_dir=str(tmp_path / "does_not_exist"),
        chroma_dir=str(tmp_path / "chroma"),
        collection_name="test",
        embeddings=FakeEmbeddings(),
    )
    assert stats.files_processed == 0
    assert stats.errors  # error recorded, no exception raised
