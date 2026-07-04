"""Orchestration tool surface for the conversational lead.

The lead agent plans work by calling *domain-action* tools (create/update work
items, read the board, propose a run) — the analogue of the file-op ``tools.py``
for the stage runtime. The port ``OrchestrationTools`` is implemented by an
adapter over the owner-scoped worker context; this module only owns the tool
specs and the (pure) dispatcher, mirroring ``execute_tool`` in ``tools.py``.
"""

from typing import Protocol

from domain.agent.llm import ToolCall, ToolResult, ToolSpec


class OrchestrationTools(Protocol):
    def list_board(self) -> str: ...

    def create_work_item(
        self, kind: str, title: str, spec: str = "", parent_id: str = ""
    ) -> str: ...

    def update_work_item(
        self, work_item_id: str, title: str = "", spec: str = "", priority: str = ""
    ) -> str: ...

    def propose_run(self, work_item_ids: list[str]) -> str: ...


ORCHESTRATION_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_board",
        description="List the project's current epic → feature → task tree so you can see what "
        "exists and choose correct parents. Call this before creating items.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="create_work_item",
        description="Create a work item. kind is 'epic', 'feature', or 'task'. Epics have no "
        "parent; a feature's parent_id must be an epic; a task's parent_id must be a feature.",
        parameters={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["epic", "feature", "task"]},
                "title": {"type": "string"},
                "spec": {"type": "string", "description": "Optional markdown description."},
                "parent_id": {"type": "string", "description": "Parent id (omit for epics)."},
            },
            "required": ["kind", "title"],
        },
    ),
    ToolSpec(
        name="update_work_item",
        description="Update an existing work item's title, spec, and/or priority.",
        parameters={
            "type": "object",
            "properties": {
                "work_item_id": {"type": "string"},
                "title": {"type": "string"},
                "spec": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            },
            "required": ["work_item_id"],
        },
    ),
    ToolSpec(
        name="propose_run",
        description="Propose starting development runs on the given work items. This posts a "
        "question in the thread that the human approves or rejects — it does not start runs "
        "directly. Propose runs on tasks (and small features), not epics.",
        parameters={
            "type": "object",
            "properties": {
                "work_item_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["work_item_ids"],
        },
    ),
]


def execute_orchestration_tool(tools: OrchestrationTools, call: ToolCall) -> ToolResult:
    """Dispatch a tool call to the capability, wrapping errors as recoverable results."""

    def ok(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text)

    def err(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text, is_error=True)

    a = call.args
    try:
        if call.name == "list_board":
            return ok(tools.list_board())
        if call.name == "create_work_item":
            return ok(tools.create_work_item(
                a["kind"], a["title"], a.get("spec", ""), a.get("parent_id", "")
            ))
        if call.name == "update_work_item":
            return ok(tools.update_work_item(
                a["work_item_id"], a.get("title", ""), a.get("spec", ""), a.get("priority", "")
            ))
        if call.name == "propose_run":
            return ok(tools.propose_run(a["work_item_ids"]))
        return err(f"unknown tool: {call.name}")
    except KeyError as exc:
        return err(f"missing argument: {exc}")
    except Exception as exc:  # domain errors (e.g. InvalidHierarchy) are recoverable in-loop
        return err(f"{type(exc).__name__}: {exc}")
