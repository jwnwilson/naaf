import uuid

import pytest
from adapters.database.engine import build_engine
from adapters.database.orm import Base
from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings
from naaf_db.engine import build_async_engine, build_async_session_factory
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def _shared_sqlite_uri():
    """A per-test unique shared-cache sqlite URI.

    Sync and async engines each get their own connection/pool, but must point at
    the SAME underlying database so routes that mix a sync UoW (e.g. an upfront
    owner-check) with an AsyncUnitOfWork (e.g. SSE hot loops) see the same data.
    Plain `sqlite://`/`sqlite+aiosqlite://` in-memory URLs each create an
    independent, isolated database per engine, which silently starves the async
    side of any tables.
    """
    return f"file:memdb_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true"


@pytest.fixture
def session_factory(_shared_sqlite_uri):
    engine = build_engine(
        f"sqlite:///{_shared_sqlite_uri}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def async_session_factory(_shared_sqlite_uri, session_factory):
    # depends on session_factory so tables exist before the async engine connects
    engine = build_async_engine(
        f"sqlite+aiosqlite:///{_shared_sqlite_uri}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return build_async_session_factory(engine)


@pytest.fixture
def client(session_factory, async_session_factory):
    app = create_app(
        settings=Settings(),
        session_factory=session_factory,
        async_session_factory=async_session_factory,
    )
    return TestClient(app)
