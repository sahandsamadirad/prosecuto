"""Session memory: typed load/save/delete/lock over a ``SessionStore``.

Implements IMPLEMENTATION_PLAN.md Phase 4. Wraps a raw ``SessionStore`` and
handles Pydantic (de)serialization, the 24h TTL, and the per-session mutex.

The factory :func:`create_session_manager` tries Redis first and silently falls
back to the in-memory store if Redis can't be pinged — it never crashes the app.
"""

from __future__ import annotations

import structlog

from app.config import settings
from app.memory.store import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionStore,
)
from app.orchestrator.state import SessionState

log = structlog.get_logger(__name__)


class SessionManager:
    """Typed persistence for :class:`SessionState`."""

    def __init__(self, store: SessionStore, ttl_hours: int | None = None) -> None:
        self.store = store
        self._ttl_seconds = int((ttl_hours or settings.session_ttl_hours) * 3600)

    @property
    def backend(self) -> str:
        return self.store.name

    async def load(self, session_id: str) -> SessionState | None:
        """Return the stored state, or ``None`` if absent/expired."""
        raw = await self.store.get(session_id)
        if raw is None:
            return None
        return SessionState.model_validate_json(raw)

    async def save(self, state: SessionState) -> None:
        """Persist state with the TTL, bumping ``updated_at`` first."""
        state.touch()
        await self.store.set(state.session_id, state.model_dump_json(), self._ttl_seconds)

    async def delete(self, session_id: str) -> None:
        await self.store.delete(session_id)

    def lock(self, session_id: str):
        """Async context manager mutex for a session.

        Usage::

            async with manager.lock(sid):
                state = await manager.load(sid)
                ...
                await manager.save(state)
        """
        return self.store.lock(session_id)

    async def close(self) -> None:
        await self.store.close()


async def create_session_manager() -> SessionManager:
    """Build a manager backed by Redis, falling back to in-memory if it's down."""
    try:
        redis_store = RedisSessionStore(settings.redis_url)
        if await redis_store.ping():
            log.info("session.backend", backend="redis", url=settings.redis_url)
            return SessionManager(redis_store)
        await redis_store.close()
    except Exception as exc:  # noqa: BLE001 — degrade, never crash
        log.warning("session.redis_init_failed", error=str(exc))

    log.warning("session.backend_fallback", backend="in-memory")
    return SessionManager(InMemorySessionStore())


# Lazily-initialized process singleton (set up in the app lifespan / on first use).
_manager: SessionManager | None = None


async def get_session_manager() -> SessionManager:
    """Return the process-wide manager, creating it on first call."""
    global _manager
    if _manager is None:
        _manager = await create_session_manager()
    return _manager
