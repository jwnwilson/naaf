"""Direct concurrency proof for the SSE event-loop-freeze fix.

Companion to ``test_activity_stream_async.py``: that test is the deterministic,
revert-discriminating guard (it asserts the streaming hot loop issues ZERO sync
queries). This test is the *behavioural* proof — it drives the real ASGI app and
shows that while several SSE streams are each parked on a slow DB poll, the event
loop stays free: the streams overlap instead of serialising, and a concurrent
``/health`` is served promptly rather than queuing behind them.

The slow poll is injected as an ``await asyncio.sleep`` in the async repository's
``list_after`` (a stand-in for a real async DB round-trip that yields the loop
during I/O). If the streams blocked the loop, N concurrent slow polls would run
end-to-end (~N*SLOW) and ``/health`` would stall behind them; because the async
UoW yields, they run concurrently (~SLOW) and ``/health`` returns in milliseconds.
"""

import asyncio
import time

import pytest
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import AgentEvent, stream_scope
from httpx import ASGITransport, AsyncClient
from interactors.api.app import create_app
from interactors.api.settings import Settings
from naaf_db.engine import (
    build_async_engine,
    build_async_session_factory,
    build_engine,
    build_session_factory,
)

SLOW = 0.3          # simulated per-poll async DB latency (seconds)
N_STREAMS = 6       # concurrent SSE viewers of the same thread
SCOPE_THREAD = "t-concurrency"


@pytest.fixture
def app(tmp_path):
    # A temp FILE sqlite (not in-memory/StaticPool) so each async session draws its
    # OWN connection from the pool — required to exercise genuine concurrency.
    db = tmp_path / "concurrency.sqlite"
    sync_engine = build_engine(f"sqlite:///{db}")
    Base.metadata.create_all(sync_engine)
    async_engine = build_async_engine(f"sqlite+aiosqlite:///{db}")

    # Seed a terminal 'final' event via the sync write path so each stream reads it,
    # yields it, and closes after exactly one (slow) poll.
    uow = SqlUnitOfWork(
        build_session_factory(sync_engine), required_filters={"owner_id": "dev-user"}
    )
    with uow.transaction():
        uow.agent_events.create(
            AgentEvent(
                owner_id="", scope=stream_scope(thread_id=SCOPE_THREAD), kind="final", payload={}
            )
        )

    return create_app(
        settings=Settings(),
        session_factory=build_session_factory(sync_engine),
        async_session_factory=build_async_session_factory(async_engine),
    )


@pytest.mark.asyncio
async def test_concurrent_streams_do_not_block_the_event_loop(app, monkeypatch):
    from adapters.database import repositories

    original = repositories.AsyncAgentEventRepository.list_after

    async def slow_list_after(self, scope, after, limit=200):
        await asyncio.sleep(SLOW)                     # yields the loop, like real async I/O
        return await original(self, scope, after, limit)

    monkeypatch.setattr(repositories.AsyncAgentEventRepository, "list_after", slow_list_after)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:

        async def open_stream():
            r = await client.get(f"/threads/{SCOPE_THREAD}/activity/stream?after=0")
            return r.status_code, r.text

        async def timed_health():
            t = time.monotonic()
            r = await client.get("/health")
            return time.monotonic() - t, r.status_code

        started = time.monotonic()
        results = await asyncio.gather(
            *[open_stream() for _ in range(N_STREAMS)],
            *[timed_health() for _ in range(N_STREAMS)],
        )
        total = time.monotonic() - started

    streams = results[:N_STREAMS]
    health = results[N_STREAMS:]

    # Every stream succeeded and actually delivered the seeded terminal event.
    assert all(code == 200 for code, _ in streams)
    assert all('"kind":"final"' in body.replace(" ", "") for _, body in streams)

    # Concurrency: N slow polls overlapped instead of serialising. Serialised would be
    # ~N*SLOW (1.8s); concurrent is ~SLOW. Assert well under half the serialised time.
    assert total < SLOW * (N_STREAMS / 2), f"streams serialised (total={total:.2f}s, SLOW={SLOW})"

    # Responsiveness: /health was served while the streams were parked on their polls,
    # not queued behind a blocked loop. Async returns in ms; a blocked loop would add ~SLOW.
    worst = max(lat for lat, _ in health)
    assert all(code == 200 for _, code in health)
    assert worst < SLOW, f"/health stalled behind streams (worst={worst:.3f}s, SLOW={SLOW})"
