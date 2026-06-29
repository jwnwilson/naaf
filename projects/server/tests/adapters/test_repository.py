import pytest
from adapters.database.orm import Base, ProjectRow, WorkItemRow
from adapters.database.ports import PaginatedResult
from adapters.database.repository import SqlRepository
from domain.errors import RecordNotFound
from domain.project import Project
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class ProjectRepo(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


def test_paginated_result_shape():
    page = PaginatedResult(results=[1, 2], total=2, page_size=50, page_number=1)
    assert page.total == 2
    assert page.results == [1, 2]


def test_orm_tables_registered():
    names = set(Base.metadata.tables.keys())
    assert {"projects", "work_items", "teams", "agent_definitions"} <= names


def test_project_row_defaults_id_and_timestamps():
    row = ProjectRow(owner_id="u1", name="naaf")
    # defaults are applied at flush, but the python-side default callables exist:
    assert row is not None
    assert ProjectRow.__table__.c.id.default is not None
    assert WorkItemRow.__table__.c.acceptance_criteria.default is not None


def test_create_stamps_owner_and_returns_dto(session):
    repo = ProjectRepo(session, required_filters={"owner_id": "u1"})
    created = repo.create(Project(owner_id="ignored", name="naaf"))
    assert isinstance(created, Project)
    assert created.owner_id == "u1"  # stamped from required_filters
    assert len(created.id) == 32
    assert created.created_at is not None


def test_read_is_owner_scoped(session):
    ProjectRepo(session, {"owner_id": "u1"}).create(Project(owner_id="u1", name="a"))
    p = ProjectRepo(session, {"owner_id": "u1"}).read_multi().results[0]
    # another owner cannot read it
    with pytest.raises(RecordNotFound):
        ProjectRepo(session, {"owner_id": "u2"}).read(p.id)


def test_read_multi_paginates_and_counts(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    for i in range(3):
        repo.create(Project(owner_id="u1", name=f"p{i}"))
    page = repo.read_multi(page_size=2, page_number=1)
    assert page.total == 3
    assert len(page.results) == 2


def test_read_multi_total_excludes_other_owners(session):
    repo1 = ProjectRepo(session, {"owner_id": "u1"})
    repo2 = ProjectRepo(session, {"owner_id": "u2"})
    for i in range(2):
        repo1.create(Project(owner_id="u1", name=f"u1-{i}"))
    for i in range(3):
        repo2.create(Project(owner_id="u2", name=f"u2-{i}"))
    page = repo1.read_multi()
    assert page.total == 2   # must NOT count u2's 3 rows
    assert len(page.results) == 2


def test_filter_like(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    repo.create(Project(owner_id="u1", name="alpha"))
    repo.create(Project(owner_id="u1", name="beta"))
    page = repo.read_multi(filters={"name__like": "alph"})
    assert page.total == 1
    assert page.results[0].name == "alpha"


def test_update_changes_fields(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    p = repo.create(Project(owner_id="u1", name="old"))
    updated = repo.update(p.id, Project(owner_id="u1", name="new"))
    assert updated.name == "new"


def test_delete_then_read_raises(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    p = repo.create(Project(owner_id="u1", name="x"))
    repo.delete(p.id)
    with pytest.raises(RecordNotFound):
        repo.read(p.id)
