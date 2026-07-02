import pytest
from adapters.agent.workspace.local import LocalWorkspace


def test_write_read_edit_roundtrip(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("a.txt", "hello world")
    assert ws.read("a.txt") == "hello world"
    ws.edit("a.txt", "world", "there")
    assert ws.read("a.txt") == "hello there"


def test_bash_runs_in_root_and_captures_exit(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("x.txt", "hi")
    r = ws.bash("ls", 10)
    assert r.exit_code == 0 and "x.txt" in r.stdout


def test_path_escape_is_rejected(tmp_path):
    ws = LocalWorkspace(tmp_path)
    with pytest.raises(ValueError):
        ws.read("../secret")
