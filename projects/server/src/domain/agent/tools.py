from domain.agent.llm import ToolCall, ToolResult, ToolSpec
from domain.agent.workspace import Workspace

BASH_TIMEOUT_S = 120

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="read_file",
        description="Read a file from the workspace.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="write_file",
        description="Create or overwrite a file.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="edit_file",
        description="Replace an exact string in a file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["path", "old", "new"],
        },
    ),
    ToolSpec(
        name="grep",
        description="Search the workspace with a regex.",
        parameters={
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"],
        },
    ),
    ToolSpec(
        name="bash",
        description="Run a shell command in the workspace.",
        parameters={
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"],
        },
    ),
    ToolSpec(
        name="report",
        description=(
            "Report the outcome of this stage and finish. Call this to end the stage with an "
            "explicit pass/fail verdict (required for the VERIFY stage)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "summary": {"type": "string"},
            },
            "required": ["passed", "summary"],
        },
    ),
]


def execute_tool(workspace: Workspace, call: ToolCall) -> ToolResult:
    def ok(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text)

    def err(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text, is_error=True)

    a = call.args
    try:
        if call.name == "read_file":
            return ok(workspace.read(a["path"]))
        if call.name == "write_file":
            workspace.write(a["path"], a["content"])
            return ok(f"wrote {a['path']}")
        if call.name == "edit_file":
            workspace.edit(a["path"], a["old"], a["new"])
            return ok(f"edited {a['path']}")
        if call.name == "grep":
            return ok(workspace.grep(a["pattern"], a.get("path")))
        if call.name == "bash":
            r = workspace.bash(a["cmd"], BASH_TIMEOUT_S)
            body = f"exit={r.exit_code}\n{r.stdout}\n{r.stderr}".strip()
            return err(body) if r.exit_code != 0 else ok(body)
        return err(f"unknown tool: {call.name}")
    except KeyError as e:
        return err(f"missing argument {e} for tool {call.name}")
    except Exception as e:  # tool errors are recoverable — report, don't crash the loop
        return err(f"{type(e).__name__}: {e}")
