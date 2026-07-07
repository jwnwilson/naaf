import json
from datetime import date, datetime

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker


def _json_default(obj: object) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_engine(db_url: str, **kwargs: object) -> Engine:
    return create_engine(
        db_url,
        future=True,
        json_serializer=lambda o: json.dumps(o, default=_json_default),
        **kwargs,
    )


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def _to_async_url(db_url: str) -> str:
    """Normalize a sync-style DB URL to its async-driver equivalent.

    `postgresql+psycopg://` is already async-capable and `sqlite+aiosqlite://` is
    already the async driver, so both pass through unchanged. Bare `sqlite://` /
    `sqlite:///...` becomes `sqlite+aiosqlite://...`, and bare `postgresql://` /
    `postgres://...` becomes `postgresql+psycopg://...` (this project uses psycopg3,
    not asyncpg).
    """
    if db_url.startswith("sqlite+aiosqlite://") or db_url.startswith("postgresql+psycopg://"):
        return db_url
    if db_url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + db_url[len("sqlite://") :]
    if db_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + db_url[len("postgresql://") :]
    if db_url.startswith("postgres://"):
        return "postgresql+psycopg://" + db_url[len("postgres://") :]
    return db_url


def build_async_engine(db_url: str, **kwargs: object) -> AsyncEngine:
    """Async engine for the given URL — sync-only schemes (bare `sqlite://` /
    `postgresql://` / `postgres://`) are normalized to their async driver first;
    already-async URLs (`sqlite+aiosqlite://`, `postgresql+psycopg://`) pass through
    unchanged."""
    return create_async_engine(
        _to_async_url(db_url),
        future=True,
        json_serializer=lambda o: json.dumps(o, default=_json_default),
        **kwargs,
    )


def build_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)
