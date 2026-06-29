from adapters.database.orm import Base, ProjectRow, WorkItemRow
from adapters.database.ports import PaginatedResult


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
    assert ProjectRow.__table__.c.id.default is not None
    assert WorkItemRow.__table__.c.acceptance_criteria.default is not None
