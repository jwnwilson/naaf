from domain.agent.llm import ToolCall
from domain.agent.tools import TOOL_SPECS, execute_tool
from domain.agent.workspace import CommandResult


class _RecordingWorkspace:
    def __init__(self): self.calls = []
    def read(self, path):
        self.calls.append(("read", path))
        return "file body"
    def write(self, path, content): self.calls.append(("write", path, content))
    def edit(self, path, old, new): self.calls.append(("edit", path, old, new))
    def grep(self, pattern, path=None): return "match"
    def bash(self, cmd, timeout_s): return CommandResult(exit_code=0, stdout="done", stderr="")


def test_tool_specs_cover_the_toolset():
    names = {t.name for t in TOOL_SPECS}
    assert names == {"read_file", "write_file", "edit_file", "grep", "bash", "report"}


def test_execute_read_file_returns_contents():
    ws = _RecordingWorkspace()
    result = execute_tool(ws, ToolCall(id="c1", name="read_file", args={"path": "a.py"}))
    assert result.tool_call_id == "c1"
    assert result.content == "file body"
    assert result.is_error is False


def test_execute_bash_reports_nonzero_as_error():
    class Failing(_RecordingWorkspace):
        def bash(self, cmd, timeout_s):
            return CommandResult(exit_code=1, stdout="", stderr="boom")
    result = execute_tool(Failing(), ToolCall(id="c2", name="bash", args={"cmd": "false"}))
    assert result.is_error is True
    assert "boom" in result.content


def test_execute_unknown_tool_is_error():
    result = execute_tool(_RecordingWorkspace(), ToolCall(id="c3", name="nope", args={}))
    assert result.is_error is True


def test_execute_missing_arg_is_error():
    result = execute_tool(_RecordingWorkspace(), ToolCall(id="c4", name="read_file", args={}))
    assert result.is_error is True
    assert "path" in result.content
