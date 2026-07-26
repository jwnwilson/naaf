import pytest
from naaf_db.engine import _to_async_url, build_async_engine, build_async_session_factory
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


@pytest.mark.asyncio
async def test_build_async_engine_accepts_bare_sync_sqlite_url():
    """A bare sync sqlite:// URL (the app's default) must not crash; it should be
    normalized to the async driver so create_app() works without naaf_db_url set."""
    engine = build_async_engine("sqlite://", connect_args={"check_same_thread": False})
    assert engine.dialect.name == "sqlite"
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await engine.dispose()


@pytest.mark.parametrize(
    ("db_url", "expected"),
    [
        ("sqlite://", "sqlite+aiosqlite://"),
        ("sqlite:///path/to.db", "sqlite+aiosqlite:///path/to.db"),
        ("postgresql+psycopg://x", "postgresql+psycopg://x"),
        ("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
        ("postgresql://u@h/db", "postgresql+psycopg://u@h/db"),
        ("postgres://u@h/db", "postgresql+psycopg://u@h/db"),
    ],
)
def test_to_async_url_normalizes_sync_schemes(db_url: str, expected: str):
    assert _to_async_url(db_url) == expected
