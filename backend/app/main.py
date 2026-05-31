"""FastAPI entrypoint for the Prosecuto backend.

Phase 0 wires up the app shell and a liveness ``/api/health`` endpoint.
Routers for HTTP (session CRUD, uploads) and WebSocket (voice/text) are
mounted in later phases.

Run locally::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging

configure_logging()
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.memory.session import get_session_manager

    # Build the session store now so the Redis→in-memory fallback (and its log
    # line) happens at startup, not on the first request.
    manager = await get_session_manager()
    app.state.session_manager = manager
    log.info(
        "prosecuto.startup",
        llm_model=settings.nim_llm_model,
        chroma_dir=str(settings.chroma_path),
        session_backend=manager.backend,
    )
    yield
    await manager.close()
    log.info("prosecuto.shutdown")


app = FastAPI(
    title="Prosecuto Backend",
    version="0.1.0",
    description="Ontario red light camera ticket dispute — AI + API services",
    lifespan=lifespan,
)

# Frontend is a separate React/Three.js app; allow it to call us in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api import http as http_router  # noqa: E402
from app.api import ws as ws_router  # noqa: E402

app.include_router(http_router.router)
app.include_router(ws_router.router)
