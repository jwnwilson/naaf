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


def test_edit_requires_single_occurrence(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("a.txt", "x x")
    with pytest.raises(ValueError):
        ws.edit("a.txt", "x", "y")   # two occurrences
    ws.write("b.txt", "hello")
    with pytest.raises(ValueError):
        ws.edit("b.txt", "zzz", "y")  # zero occurrences


def test_bash_timeout_returns_124(tmp_path):
    ws = LocalWorkspace(tmp_path)
    r = ws.bash("sleep 5", 1)
    assert r.exit_code == 124
    assert "timeout" in r.stderr


def test_grep_finds_matches(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("a.txt", "needle here")
    assert "needle" in ws.grep("needle", None)
