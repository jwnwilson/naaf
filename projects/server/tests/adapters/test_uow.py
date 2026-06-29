import pytest
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _uow(factory):
    return SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})


def test_transaction_commits_multiple_writes_atomically(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        proj = uow.projects.create(Project(owner_id="u1", name="naaf"))
        uow.work_items.create(
            WorkItem(owner_id="u1", project_id=proj.id, kind=WorkItemKind.EPIC, title="Auth")
        )
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 1
    assert uow2.work_items.read_multi().total == 1


def test_transaction_rolls_back_on_error(session_factory):
    uow = _uow(session_factory)
    with pytest.raises(RuntimeError):
        with uow.transaction():
            uow.projects.create(Project(owner_id="u1", name="naaf"))
            raise RuntimeError("boom")
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 0
