import pytest
from adapters.database.orm import Base
from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(session_factory):
    app = create_app(settings=Settings(), session_factory=session_factory)
    return TestClient(app)
