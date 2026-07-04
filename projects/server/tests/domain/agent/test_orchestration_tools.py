from domain.agent.llm import ToolCall
from domain.agent.orchestration import (
    ORCHESTRATION_TOOL_SPECS,
    execute_orchestration_tool,
)


class FakeTools:
    def __init__(self) -> None:
        self.calls: list = []

    def list_board(self) -> str:
        self.calls.append(("list_board",))
        return "EPIC Auth"

    def create_work_item(self, kind, title, spec="", parent_id="") -> str:
        self.calls.append(("create", kind, title, spec, parent_id))
        return f"created {kind} '{title}' id=wi9"

    def update_work_item(self, work_item_id, title="", spec="", priority="") -> str:
        self.calls.append(("update", work_item_id, title, spec, priority))
        return "updated"

    def propose_run(self, work_item_ids) -> str:
        self.calls.append(("propose", tuple(work_item_ids)))
        return f"proposed run on {len(work_item_ids)} items"


def _call(name, args):
    return ToolCall(id="t1", name=name, args=args)


def test_specs_cover_the_orchestration_surface():
    names = {s.name for s in ORCHESTRATION_TOOL_SPECS}
    assert names == {"list_board", "create_work_item", "update_work_item", "propose_run"}


def test_dispatches_create_work_item():
    tools = FakeTools()
    call = _call("create_work_item", {"kind": "task", "title": "Add login", "parent_id": "f1"})
    res = execute_orchestration_tool(tools, call)
    assert res.is_error is False
    assert "created task" in res.content
    assert tools.calls == [("create", "task", "Add login", "", "f1")]


def test_dispatches_propose_run():
    tools = FakeTools()
    res = execute_orchestration_tool(tools, _call("propose_run", {"work_item_ids": ["a", "b"]}))
    assert "2 items" in res.content
    assert tools.calls == [("propose", ("a", "b"))]


def test_missing_argument_is_a_recoverable_error():
    tools = FakeTools()
    res = execute_orchestration_tool(tools, _call("create_work_item", {"kind": "task"}))
    assert res.is_error is True
    assert "missing argument" in res.content


def test_unknown_tool_is_an_error():
    res = execute_orchestration_tool(FakeTools(), _call("delete_everything", {}))
    assert res.is_error is True
