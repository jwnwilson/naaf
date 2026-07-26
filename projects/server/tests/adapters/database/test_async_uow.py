import pytest
from adapters.database.orm import Base
from adapters.database.uow import AsyncUnitOfWork
from domain.agent.events import AgentEvent, stream_scope
from naaf_db.engine import build_async_engine, build_async_session_factory
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def async_factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield build_async_session_factory(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_agent_events_list_after(async_factory):
    scope = stream_scope(thread_id="t1")
    uow = AsyncUnitOfWork(async_factory, required_filters={"owner_id": "u1"})
    async with uow.transaction():
        await uow.agent_events.create(
            AgentEvent(owner_id="", scope=scope, kind="status", payload={})
        )
        await uow.agent_events.create(
            AgentEvent(owner_id="", scope=scope, kind="final", payload={})
        )
    async with uow.transaction():
        events = await uow.agent_events.list_after(scope, after=0, limit=10)
    assert [e.kind for e in events] == ["status", "final"]
    assert events[0].seq < events[1].seq
