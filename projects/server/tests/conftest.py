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
def session_factory():
    engine = build_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def async_session_factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
