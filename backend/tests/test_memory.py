"""Phase 4 tests: session store + manager, fallback, TTL, and the lock.

Covers IMPLEMENTATION_PLAN.md Phase 4 "done when":
* save a SessionState, load it back, assert equality;
* in-memory fallback works when the Redis URL is unreachable;
* concurrent save/load under the lock works (two asyncio tasks, no lost update).
"""

from __future__ import annotations

import asyncio

import pytest

from app.memory.session import SessionManager, create_session_manager
from app.memory.store import InMemorySessionStore, RedisSessionStore
from app.orchestrator.state import SessionState


def _state(sid="s1", mode="lawyer") -> SessionState:
    st = SessionState(session_id=sid, mode=mode)
    st.add_turn("user", "I got a red light camera ticket")
    return st


async def test_save_load_roundtrip_equality():
    mgr = SessionManager(InMemorySessionStore())
    st = _state()
    await mgr.save(st)
    loaded = await mgr.load("s1")
    assert loaded is not None
    assert loaded.session_id == st.session_id
    assert loaded.last_user_message == "I got a red light camera ticket"
    assert loaded.transcript[0].content == st.transcript[0].content


async def test_load_missing_returns_none():
    mgr = SessionManager(InMemorySessionStore())
    assert await mgr.load("nope") is None


async def test_delete_removes_state():
    mgr = SessionManager(InMemorySessionStore())
    await mgr.save(_state())
    await mgr.delete("s1")
    assert await mgr.load("s1") is None


async def test_ttl_expiry_in_memory():
    mgr = SessionManager(InMemorySessionStore(), ttl_hours=0)  # 0 → no expiry path
    # Force a tiny TTL directly through the store to exercise expiry.
    await mgr.store.set("s1", _state().model_dump_json(), ttl_seconds=-1)
    # ttl<=0 means "no expiry" in our store, so it persists.
    assert await mgr.store.get("s1") is not None

    # Now a genuinely-expired entry: patch monotonic via a short positive TTL.
    import time

    await mgr.store.set("s2", "{}", ttl_seconds=1)
    real = time.monotonic
    try:
        time.monotonic = lambda: real() + 5  # jump past expiry
        assert await mgr.store.get("s2") is None
    finally:
        time.monotonic = real


async def test_redis_unreachable_falls_back_to_in_memory(monkeypatch):
    # Point Redis at a dead port; create_session_manager must not raise.
    from app.config import settings

    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:6390/0")
    mgr = await create_session_manager()
    assert mgr.backend == "in-memory"
    # And it's fully functional.
    await mgr.save(_state())
    assert (await mgr.load("s1")) is not None


async def test_redis_store_ping_false_when_down():
    store = RedisSessionStore("redis://127.0.0.1:6390/0")
    assert await store.ping() is False
    await store.close()


async def test_concurrent_updates_under_lock_no_lost_update():
    """Two tasks each append N turns under the lock; all 2N must survive."""
    mgr = SessionManager(InMemorySessionStore())
    await mgr.save(SessionState(session_id="s1", mode="lawyer"))

    async def worker(label: str, n: int):
        for i in range(n):
            async with mgr.lock("s1"):
                st = await mgr.load("s1")
                st.add_turn("user", f"{label}-{i}")
                await mgr.save(st)
            await asyncio.sleep(0)  # yield to interleave tasks

    n = 10
    await asyncio.gather(worker("a", n), worker("b", n))

    final = await mgr.load("s1")
    assert len(final.transcript) == 2 * n  # no lost updates


async def test_concurrent_without_lock_can_lose_updates():
    """Sanity: without the lock, interleaving loses updates (proves the lock matters)."""
    mgr = SessionManager(InMemorySessionStore())
    await mgr.save(SessionState(session_id="s1", mode="lawyer"))

    async def worker(label: str, n: int):
        for i in range(n):
            st = await mgr.load("s1")
            st.add_turn("user", f"{label}-{i}")
            await asyncio.sleep(0)  # force interleave between load and save
            await mgr.save(st)

    n = 10
    await asyncio.gather(worker("a", n), worker("b", n))
    final = await mgr.load("s1")
    assert len(final.transcript) < 2 * n  # updates were lost without the lock
