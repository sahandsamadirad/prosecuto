"""Session storage backends (IMPLEMENTATION_PLAN.md Phase 4).

Two interchangeable implementations behind one ``SessionStore`` interface:

* ``RedisSessionStore``    — durable, resumable sessions (production).
* ``InMemorySessionStore`` — dev / test fallback when Redis is unreachable.

Stores hold raw JSON strings keyed by ``session_id`` and expose a per-session
async mutex. (De)serialization and key semantics live one layer up in
``session.py``. Redis schema (ARCHITECTURE §9):

    session:{session_id}        → JSON SessionState (TTL: settings.session_ttl_hours)
    session:{session_id}:lock   → mutex for concurrent updates
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog

log = structlog.get_logger(__name__)


def _key(session_id: str) -> str:
    return f"session:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"session:{session_id}:lock"


class SessionStore(ABC):
    """Raw key/value store for serialized session state + a per-session lock."""

    name: str = "abstract"

    @abstractmethod
    async def get(self, session_id: str) -> str | None: ...

    @abstractmethod
    async def set(self, session_id: str, data: str, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def delete(self, session_id: str) -> None: ...

    @abstractmethod
    def lock(self, session_id: str) -> "AsyncContextManagerLike": ...

    @abstractmethod
    async def ping(self) -> bool: ...

    async def close(self) -> None:  # optional
        return None


# Structural type for "thing usable with `async with`".
AsyncContextManagerLike = object


class InMemorySessionStore(SessionStore):
    """Process-local dict store with TTL and per-session ``asyncio.Lock``.

    Used in dev/tests and as the automatic fallback when Redis is down. State is
    lost on restart — that's acceptable for the fallback path.
    """

    name = "in-memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, session_id: str) -> str | None:
        entry = self._data.get(_key(session_id))
        if entry is None:
            return None
        data, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._data.pop(_key(session_id), None)
            return None
        return data

    async def set(self, session_id: str, data: str, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None
        self._data[_key(session_id)] = (data, expires_at)

    async def delete(self, session_id: str) -> None:
        self._data.pop(_key(session_id), None)

    def lock(self, session_id: str) -> asyncio.Lock:
        # Same Lock object per session_id → real mutual exclusion.
        return self._locks.setdefault(_lock_key(session_id), asyncio.Lock())

    async def ping(self) -> bool:
        return True


class RedisSessionStore(SessionStore):
    """Durable Redis-backed store using ``redis.asyncio``."""

    name = "redis"

    def __init__(self, url: str, lock_timeout: int = 30, lock_blocking_timeout: int = 10) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(url, decode_responses=True)
        self._lock_timeout = lock_timeout
        self._lock_blocking_timeout = lock_blocking_timeout

    async def get(self, session_id: str) -> str | None:
        return await self._client.get(_key(session_id))

    async def set(self, session_id: str, data: str, ttl_seconds: int) -> None:
        if ttl_seconds > 0:
            await self._client.set(_key(session_id), data, ex=ttl_seconds)
        else:
            await self._client.set(_key(session_id), data)

    async def delete(self, session_id: str) -> None:
        await self._client.delete(_key(session_id))

    def lock(self, session_id: str):
        # redis.asyncio Lock is an async context manager; the key enforces the
        # cross-process mutex. timeout auto-releases to avoid deadlocks.
        return self._client.lock(
            _lock_key(session_id),
            timeout=self._lock_timeout,
            blocking=True,
            blocking_timeout=self._lock_blocking_timeout,
        )

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception as exc:  # noqa: BLE001 — never crash on a dead Redis
            log.warning("redis.ping_failed", error=str(exc))
            return False

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # noqa: BLE001
            pass


@asynccontextmanager
async def nullcontext_lock() -> AsyncIterator[None]:
    """A no-op async lock (used only where locking is intentionally skipped)."""
    yield
