"""Phase 7 tests: REST API integration via FastAPI TestClient.

Covers session lifecycle, upload + size limit, package retrieval, admin auth,
and 4xx behaviour for missing/invalid session IDs (IMPLEMENTATION_PLAN Phase 7).
"""

from __future__ import annotations

import asyncio
import io

from fastapi.testclient import TestClient

from app.main import app
from app.memory.session import get_session_manager
from app.schemas.packages import ERPackage

client = TestClient(app)


def _new_session(mode="lawyer") -> str:
    r = client.post("/api/session", json={"mode": mode})
    assert r.status_code == 200
    return r.json()["session_id"]


# --- Session lifecycle ----------------------------------------------------


def test_create_session_returns_id_and_mode():
    r = client.post("/api/session", json={"mode": "lawyer"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "lawyer"
    assert body["session_id"]


def test_create_judge_session_initializes_court_phase():
    sid = _new_session("judge")
    r = client.get(f"/api/session/{sid}")
    assert r.status_code == 200
    assert r.json()["court_phase"] == "idle"


def test_get_session_roundtrip_and_404():
    sid = _new_session()
    r = client.get(f"/api/session/{sid}")
    assert r.status_code == 200
    assert r.json()["session_id"] == sid
    assert client.get("/api/session/does-not-exist").status_code == 404


def test_delete_session_and_404():
    sid = _new_session()
    assert client.delete(f"/api/session/{sid}").status_code == 200
    assert client.get(f"/api/session/{sid}").status_code == 404  # gone
    assert client.delete("/api/session/nope").status_code == 404


def test_invalid_mode_rejected():
    assert client.post("/api/session", json={"mode": "wizard"}).status_code == 422


# --- Upload ---------------------------------------------------------------


def test_upload_ticket_photo():
    sid = _new_session()
    data = b"\x89PNG fake image bytes"
    r = client.post(
        f"/api/session/{sid}/upload",
        files={"file": ("ticket.png", io.BytesIO(data), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "ticket.png"
    assert body["size"] == len(data)
    session = client.get(f"/api/session/{sid}").json()
    assert session["uploaded_files"] == ["ticket.png"]


def test_upload_to_missing_session_404():
    r = client.post(
        "/api/session/missing/upload",
        files={"file": ("t.png", io.BytesIO(b"x"), "image/png")},
    )
    assert r.status_code == 404


def test_upload_size_limit_enforced():
    sid = _new_session()
    big = b"0" * (10 * 1024 * 1024 + 1)  # just over 10MB
    r = client.post(
        f"/api/session/{sid}/upload",
        files={"file": ("big.bin", io.BytesIO(big), "application/octet-stream")},
    )
    assert r.status_code == 413


# --- Package --------------------------------------------------------------


def test_package_404_until_produced_then_200():
    sid = _new_session()
    assert client.get(f"/api/session/{sid}/package").status_code == 404

    async def inject():
        mgr = await get_session_manager()
        st = await mgr.load(sid)
        st.er_package = ERPackage(summary="ER plan", confidence="high")
        await mgr.save(st)

    asyncio.run(inject())

    r = client.get(f"/api/session/{sid}/package")
    assert r.status_code == 200
    assert r.json()["kind"] == "early_resolution"


# --- Admin rebuild --------------------------------------------------------


def test_rebuild_index_requires_admin_token(monkeypatch):
    from app.config import settings

    # Not configured → 503.
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.post("/api/index/rebuild").status_code == 503

    # Configured but wrong/missing header → 401.
    monkeypatch.setattr(settings, "admin_token", "secret")
    assert client.post("/api/index/rebuild").status_code == 401
    assert client.post(
        "/api/index/rebuild", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401


def test_rebuild_index_runs_with_valid_token(monkeypatch):
    from app.config import settings
    from app.rag.indexer import IndexStats

    monkeypatch.setattr(settings, "admin_token", "secret")
    # Avoid real embedding work — stub the indexer and embeddings.
    monkeypatch.setattr(
        "app.rag.indexer.build_index",
        lambda **kw: IndexStats(files_processed=3, chunks_created=12),
    )
    monkeypatch.setattr("app.rag.embeddings.get_embeddings", lambda prefer=None: object())

    r = client.post(
        "/api/index/rebuild",
        headers={"Authorization": "Bearer secret"},
        json={"embedder": "local"},
    )
    assert r.status_code == 200
    assert r.json()["chunks_created"] == 12
