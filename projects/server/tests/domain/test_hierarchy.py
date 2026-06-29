import pytest
from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.work_item import WorkItem
from domain.work_item import WorkItemKind as K


def _item(kind: K) -> WorkItem:
    return WorkItem(owner_id="u1", project_id="p1", kind=kind, title="x")


def test_epic_must_be_root():
    validate_hierarchy(K.EPIC, None)  # no raise


def test_epic_with_parent_is_rejected():
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.EPIC, _item(K.EPIC))


def test_feature_parent_must_be_epic():
    validate_hierarchy(K.FEATURE, _item(K.EPIC))  # no raise
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.FEATURE, None)
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.FEATURE, _item(K.FEATURE))


def test_task_parent_must_be_feature():
    validate_hierarchy(K.TASK, _item(K.FEATURE))  # no raise
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.TASK, _item(K.EPIC))
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.TASK, None)
