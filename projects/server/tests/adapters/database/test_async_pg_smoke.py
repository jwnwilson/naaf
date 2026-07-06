import os

import pytest

PG = os.environ.get("NAAF_TEST_PG_URL")  # e.g. postgresql+psycopg://naaf:naaf@localhost:5432/naaf


@pytest.mark.skipif(not PG, reason="set NAAF_TEST_PG_URL to run the Postgres async smoke test")
@pytest.mark.asyncio
async def test_async_uow_reads_agent_events_on_postgres():
    from adapters.database.uow import AsyncUnitOfWork
    from domain.agent.events import stream_scope
    from naaf_db.engine import build_async_engine, build_async_session_factory

    engine = build_async_engine(PG)
    factory = build_async_session_factory(engine)
    uow = AsyncUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    async with uow.transaction():
        # read-only: must not raise and must return a list
        rows = await uow.agent_events.list_after(stream_scope(thread_id="nonexistent"), 0, 10)
    assert rows == []
    await engine.dispose()
