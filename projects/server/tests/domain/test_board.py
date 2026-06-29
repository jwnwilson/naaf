from domain.board import build_board_tree
from domain.work_item import WorkItem, WorkItemKind as K


def _item(id_: str, kind: K, parent_id: str | None) -> WorkItem:
    return WorkItem(id=id_, owner_id="u1", project_id="p1", kind=kind,
                    title=id_, parent_id=parent_id)


def test_builds_epic_feature_task_tree():
    items = [
        _item("e", K.EPIC, None),
        _item("f", K.FEATURE, "e"),
        _item("t", K.TASK, "f"),
    ]
    roots = build_board_tree(items)
    assert len(roots) == 1
    assert roots[0].item.id == "e"
    assert roots[0].children[0].item.id == "f"
    assert roots[0].children[0].children[0].item.id == "t"


def test_multiple_roots_and_empty():
    assert build_board_tree([]) == []
    roots = build_board_tree([_item("e1", K.EPIC, None), _item("e2", K.EPIC, None)])
    assert {r.item.id for r in roots} == {"e1", "e2"}


def test_orphan_is_dropped():
    roots = build_board_tree([_item("f", K.FEATURE, "missing")])
    assert roots == []
