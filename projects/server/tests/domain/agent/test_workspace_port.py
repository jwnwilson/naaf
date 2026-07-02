from domain.agent.workspace import CommandResult, Workspace


class _StubWorkspace:
    def read(self, path): return "content"
    def write(self, path, content): return None
    def edit(self, path, old, new): return None
    def grep(self, pattern, path=None): return ""
    def bash(self, cmd, timeout_s): return CommandResult(exit_code=0, stdout="ok", stderr="")


def test_stub_satisfies_workspace_protocol():
    ws: Workspace = _StubWorkspace()
    assert ws.bash("ls", 5).exit_code == 0
    assert ws.read("x") == "content"
