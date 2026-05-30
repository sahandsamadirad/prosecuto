"""Corpus indexer: a directory of ``.txt`` files → embedded chunks in ChromaDB.

Implements ARCHITECTURE.md section 7 / IMPLEMENTATION_PLAN.md Phase 1, built on
LangChain primitives (mirrors the reference Self-RAG ``ingestion`` pattern):
``RecursiveCharacterTextSplitter`` → ``Document`` objects → ``langchain_chroma.Chroma``.

Reusable, idempotent, takes a directory path as input. Re-indexing the same
file produces the *same* chunk IDs (``sha256(source_path:chunk_index)``); the
Chroma vectorstore upserts by ID, so re-runs overwrite in place rather than
duplicating.

CLI::

    python -m app.rag.indexer \
        --corpus-dir backend/data/corpus \
        --chroma-dir backend/data/chroma \
        --collection prosecuto
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import structlog
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from app.config import settings
from app.rag.embeddings import get_embeddings

log = structlog.get_logger(__name__)

# Separators in priority order, per ARCHITECTURE.md section 7 step 3.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
ADD_BATCH_SIZE = 32


class IndexStats(BaseModel):
    """Outcome of an indexing run."""

    files_processed: int = 0
    chunks_created: int = 0
    files_skipped: int = 0
    errors: list[str] = Field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover — cosmetic
        return (
            f"files_processed={self.files_processed} "
            f"chunks_created={self.chunks_created} "
            f"files_skipped={self.files_skipped} "
            f"errors={len(self.errors)}"
        )


def _chunk_id(source_path: str, chunk_index: int) -> str:
    """Deterministic, collision-resistant chunk ID for idempotent upserts."""
    return hashlib.sha256(f"{source_path}:{chunk_index}".encode()).hexdigest()


def get_vectorstore(
    embeddings: Embeddings | None = None,
    chroma_dir: str | None = None,
    collection_name: str | None = None,
) -> Chroma:
    """Open (or create) the persistent LangChain ``Chroma`` vectorstore.

    Shared by the indexer (write) and the retriever (read) so both sides use
    the same collection, embedding backend, and distance space.
    """
    return Chroma(
        collection_name=collection_name or settings.chroma_collection,
        embedding_function=embeddings or get_embeddings(),
        persist_directory=str(Path(chroma_dir or settings.chroma_path).resolve()),
        collection_metadata={"hnsw:space": "cosine"},
    )


def build_index(
    corpus_dir: str | None = None,
    chroma_dir: str | None = None,
    collection_name: str = "prosecuto",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    glob_pattern: str = "**/*.txt",
    embeddings: Embeddings | None = None,
) -> IndexStats:
    """Index every file matching ``glob_pattern`` under ``corpus_dir`` into Chroma.

    Idempotent: chunk IDs are derived from ``source_path`` + ``chunk_index``,
    so re-running over an unchanged corpus leaves the collection count stable.
    """
    corpus_dir = corpus_dir or str(settings.corpus_path)
    chroma_dir = chroma_dir or str(settings.chroma_path)
    embeddings = embeddings or get_embeddings()

    corpus_root = Path(corpus_dir).resolve()
    stats = IndexStats()

    if not corpus_root.exists():
        stats.errors.append(f"corpus_dir does not exist: {corpus_root}")
        log.error("indexer.no_corpus_dir", corpus_dir=str(corpus_root))
        return stats

    store = get_vectorstore(embeddings, chroma_dir, collection_name)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        add_start_index=True,
    )

    files = sorted(p for p in corpus_root.rglob(glob_pattern) if p.is_file())
    log.info(
        "indexer.start",
        corpus_dir=str(corpus_root),
        files_found=len(files),
        embedder=getattr(embeddings, "name", type(embeddings).__name__),
        collection=collection_name,
    )

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"read {path}: {exc}")
            stats.files_skipped += 1
            log.warning("indexer.read_failed", path=str(path), error=str(exc))
            continue

        if not text.strip():
            stats.files_skipped += 1
            log.warning("indexer.empty_file", path=str(path))
            continue

        rel_path = str(path.relative_to(corpus_root))
        docs = _make_chunks(text, rel_path, path.name, splitter)

        try:
            _add_in_batches(store, docs)
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"index {path}: {exc}")
            stats.files_skipped += 1
            log.warning("indexer.index_failed", path=str(path), error=str(exc))
            continue

        stats.files_processed += 1
        stats.chunks_created += len(docs)
        log.info("indexer.file_done", path=rel_path, chunks=len(docs))

    log.info("indexer.done", **stats.model_dump(exclude={"errors"}))
    return stats


def _make_chunks(
    text: str,
    source_path: str,
    filename: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """Split a document into LangChain ``Document`` chunks with full metadata."""
    raw = splitter.create_documents([text])
    total = len(raw)
    chunks: list[Document] = []
    for i, doc in enumerate(raw):
        char_start = int(doc.metadata.get("start_index", 0))
        doc.metadata = {
            "source_path": source_path,
            "filename": filename,
            "chunk_index": i,
            "char_start": char_start,
            "char_end": char_start + len(doc.page_content),
            "total_chunks": total,
        }
        doc.id = _chunk_id(source_path, i)
        chunks.append(doc)
    return chunks


def _add_in_batches(store: Chroma, docs: list[Document], batch_size: int = ADD_BATCH_SIZE) -> None:
    """Embed and upsert in batches of ``batch_size`` (default 32).

    ``Chroma.add_documents`` upserts by ID, so stable IDs make this idempotent.
    """
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        store.add_documents(batch, ids=[d.id for d in batch])


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index a corpus into ChromaDB.")
    parser.add_argument("--corpus-dir", default=str(settings.corpus_path))
    parser.add_argument("--chroma-dir", default=str(settings.chroma_path))
    parser.add_argument("--collection", default=settings.chroma_collection)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=200)
    parser.add_argument("--glob", default="**/*.txt")
    parser.add_argument(
        "--embedder",
        choices=["auto", "nvidia", "local"],
        default="auto",
        help="Force an embedding backend. 'auto' uses NVIDIA when a key is set.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    prefer = None if args.embedder == "auto" else args.embedder
    stats = build_index(
        corpus_dir=args.corpus_dir,
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        glob_pattern=args.glob,
        embeddings=get_embeddings(prefer=prefer),
    )
    print(f"Index complete: {stats}")
    if stats.errors:
        print("Errors:")
        for err in stats.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
