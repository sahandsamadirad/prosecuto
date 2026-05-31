"""REST API — session lifecycle, uploads, package retrieval, admin, health.

Implements ARCHITECTURE.md section 11 / IMPLEMENTATION_PLAN.md Phase 7. Handlers
are thin: they marshal requests and delegate to the session store and indexer.
All business logic lives in the orchestrator/agents, never here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.memory.session import SessionManager, get_session_manager
from app.orchestrator.state import CourtPhase, SessionState

log = structlog.get_logger(__name__)

router = APIRouter(tags=["api"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_UPLOAD_CHUNK = 1 * 1024 * 1024


# --- Dependency -----------------------------------------------------------


async def get_manager() -> SessionManager:
    return await get_session_manager()


async def _require_session(session_id: str, mgr: SessionManager) -> SessionState:
    structlog.contextvars.bind_contextvars(session_id=session_id)
    state = await mgr.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return state


# --- Request/response models ---------------------------------------------


class CreateSessionRequest(BaseModel):
    mode: Literal["lawyer", "judge"]


class CreateSessionResponse(BaseModel):
    session_id: str
    mode: Literal["lawyer", "judge"]


class RebuildIndexRequest(BaseModel):
    corpus_dir: str | None = None
    chroma_dir: str | None = None
    collection: str | None = None
    embedder: Literal["auto", "nvidia", "local"] = "auto"


# --- Session lifecycle ----------------------------------------------------


@router.post("/api/session", response_model=CreateSessionResponse)
async def create_session(body: CreateSessionRequest, mgr: SessionManager = Depends(get_manager)):
    session_id = str(uuid4())
    state = SessionState(session_id=session_id, mode=body.mode)
    if body.mode == "judge":
        state.court_phase = CourtPhase.IDLE
        state.court_transcript = []
    await mgr.save(state)
    log.info("api.session_created", session_id=session_id, mode=body.mode)
    return CreateSessionResponse(session_id=session_id, mode=body.mode)


@router.get("/api/session/{session_id}", response_model=SessionState)
async def get_session(session_id: str, mgr: SessionManager = Depends(get_manager)):
    return await _require_session(session_id, mgr)


@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str, mgr: SessionManager = Depends(get_manager)):
    await _require_session(session_id, mgr)
    await mgr.delete(session_id)
    return {"status": "deleted", "session_id": session_id}


# --- Upload ---------------------------------------------------------------


@router.post("/api/session/{session_id}/upload")
async def upload_ticket(
    session_id: str,
    file: UploadFile = File(...),
    mgr: SessionManager = Depends(get_manager),
):
    state = await _require_session(session_id, mgr)

    dest_dir = settings.uploads_path / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    dest = dest_dir / safe_name

    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(_UPLOAD_CHUNK):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file exceeds 10MB limit")
            out.write(chunk)

    log.info("api.upload", session_id=session_id, filename=safe_name, size=size)
    if safe_name not in state.uploaded_files:
        state.uploaded_files.append(safe_name)
        state.touch()
        await mgr.save(state)
    return {"filename": safe_name, "size": size, "path": str(dest)}


# --- Package --------------------------------------------------------------


@router.get("/api/session/{session_id}/package")
async def get_package(session_id: str, mgr: SessionManager = Depends(get_manager)):
    state = await _require_session(session_id, mgr)
    package = state.finalized_package()
    if package is None:
        raise HTTPException(status_code=404, detail="no package produced yet")
    return package


# --- Admin: rebuild index -------------------------------------------------


def _check_admin(authorization: str | None) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="admin token not configured")
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing admin token")


@router.post("/api/index/rebuild")
async def rebuild_index(
    body: RebuildIndexRequest | None = None,
    authorization: str | None = Header(default=None),
):
    _check_admin(authorization)
    body = body or RebuildIndexRequest()

    from app.rag.embeddings import get_embeddings
    from app.rag.indexer import build_index

    prefer = None if body.embedder == "auto" else body.embedder
    stats = await asyncio.to_thread(
        build_index,
        corpus_dir=body.corpus_dir or str(settings.corpus_path),
        chroma_dir=body.chroma_dir or str(settings.chroma_path),
        collection_name=body.collection or settings.chroma_collection,
        embeddings=get_embeddings(prefer=prefer),
    )
    log.info("api.index_rebuilt", **stats.model_dump(exclude={"errors"}))
    return stats


# --- Health ---------------------------------------------------------------


@router.get("/api/health")
async def health(mgr: SessionManager = Depends(get_manager)):
    """Liveness + dependency checks (Redis, Chroma, NIM config)."""
    checks: dict = {}

    # Active session store (redis when reachable, else in-memory fallback).
    try:
        checks["session_store"] = {"backend": mgr.backend, "ok": await mgr.store.ping()}
    except Exception as exc:  # noqa: BLE001
        checks["session_store"] = {"backend": mgr.backend, "ok": False, "error": str(exc)}

    # Chroma — count the collection without spinning up an embedder.
    chroma_ok = False
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.chroma_path))
        coll = client.get_or_create_collection(settings.chroma_collection)
        checks["chroma"] = {"ok": True, "count": coll.count()}
        chroma_ok = True
    except Exception as exc:  # noqa: BLE001
        checks["chroma"] = {"ok": False, "error": str(exc)}

    # NIM — report configuration, not a live call (avoid per-healthcheck latency).
    checks["nim"] = {
        "configured": bool(settings.nvidia_api_key),
        "llm_model": settings.nim_llm_model,
    }

    status = "ok" if chroma_ok else "degraded"
    return {"status": status, "checks": checks}
