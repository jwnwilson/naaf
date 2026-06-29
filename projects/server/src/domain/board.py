from __future__ import annotations

from pydantic import BaseModel, Field

from domain.work_item import WorkItem


class BoardNode(BaseModel):
    item: WorkItem
    children: list[BoardNode] = Field(default_factory=list)


def build_board_tree(items: list[WorkItem]) -> list[BoardNode]:
    """Nest a flat list of work items into a parent/child forest.

    Items whose parent_id is not present in the input are dropped (not a root).
    """
    nodes: dict[str, BoardNode] = {i.id: BoardNode(item=i) for i in items}
    roots: list[BoardNode] = []
    for item in items:
        node = nodes[item.id]
        if item.parent_id is None:
            roots.append(node)
        elif item.parent_id in nodes:
            nodes[item.parent_id].children.append(node)
        # else: orphan -> dropped
    return roots
