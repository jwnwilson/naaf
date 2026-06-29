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
