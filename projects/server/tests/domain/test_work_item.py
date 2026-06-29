from datetime import datetime

from domain.base import Entity, new_id, utcnow
from domain.errors import (
    DomainError,
    IntegrityConflict,
    InvalidHierarchy,
    InvalidTransition,
    RecordNotFound,
)


def test_new_id_is_32_char_hex():
    value = new_id()
    assert len(value) == 32
    assert all(c in "0123456789abcdef" for c in value)


def test_utcnow_returns_datetime():
    assert isinstance(utcnow(), datetime)


def test_entity_gets_default_id():
    a = Entity()
    b = Entity()
    assert len(a.id) == 32
    assert a.id != b.id


def test_record_not_found_is_domain_error():
    assert issubclass(RecordNotFound, DomainError)


def test_integrity_conflict_is_domain_error():
    assert issubclass(IntegrityConflict, DomainError)


def test_invalid_transition_is_domain_error():
    assert issubclass(InvalidTransition, DomainError)


def test_invalid_hierarchy_is_domain_error():
    assert issubclass(InvalidHierarchy, DomainError)


from domain.work_item import (
    AcceptanceCriterion,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


def test_work_item_defaults():
    item = WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert item.status is WorkItemStatus.TO_DO
    assert item.parent_id is None
    assert item.acceptance_criteria == []
    assert len(item.id) == 32


def test_work_item_is_immutable_via_model_copy():
    item = WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.TASK, title="x")
    updated = item.model_copy(update={"status": WorkItemStatus.IN_PROGRESS})
    assert item.status is WorkItemStatus.TO_DO  # original untouched
    assert updated.status is WorkItemStatus.IN_PROGRESS


def test_acceptance_criterion_defaults_not_done():
    crit = AcceptanceCriterion(text="returns 200")
    assert crit.done is False
