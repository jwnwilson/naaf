import pytest
from naaf_db.engine import build_async_engine, build_async_session_factory
from sqlalchemy import text
from sqlalchemy.pool import StaticPool


@pytest.mark.asyncio
async def test_async_session_executes_a_query():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = build_async_session_factory(engine)
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await engine.dispose()
