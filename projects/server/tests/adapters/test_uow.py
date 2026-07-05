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


def test_delete_where_respects_owner_and_in_filter(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.api.schemas import CreateProject

    a = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a.transaction():
        p1 = a.projects.create(CreateProject(name="p1"))
        p2 = a.projects.create(CreateProject(name="p2"))

    other = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with other.transaction():
        pb = other.projects.create(CreateProject(name="pb"))

    a2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a2.transaction():
        removed = a2.projects.delete_where(id__in=[p1.id, p2.id, pb.id])
        assert removed == 2  # pb belongs to owner "b" and is filtered out

    b2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with b2.transaction():
        assert b2.projects.read(pb.id).id == pb.id  # untouched


def test_delete_where_cannot_bypass_owner_scope(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.api.schemas import CreateProject

    owner_b = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with owner_b.transaction():
        pb = owner_b.projects.create(CreateProject(name="pb"))

    # Owner "a" tries to delete owner "b"'s row by passing owner_id explicitly.
    owner_a = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with owner_a.transaction():
        removed = owner_a.projects.delete_where(owner_id="b", id=pb.id)
        assert removed == 0  # required owner scope ("a") wins; nothing matches

    check_b = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with check_b.transaction():
        assert check_b.projects.read(pb.id).id == pb.id  # untouched
