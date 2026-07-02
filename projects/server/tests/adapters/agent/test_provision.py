import subprocess
from pathlib import Path

from adapters.agent.provision import provision_workspace


def _init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)


def test_provision_clones_repo_and_creates_agent_branch(tmp_path):
    src = tmp_path / "src"
    _init_repo(src)
    ws = provision_workspace(str(src), "run123", str(tmp_path / "ws"))
    ws_path = Path(ws)
    assert (ws_path / "README.md").read_text() == "hello"  # repo cloned
    branch = subprocess.run(
        ["git", "-C", ws, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "agent/run123"


def test_provision_is_idempotent(tmp_path):
    src = tmp_path / "src"
    _init_repo(src)
    root = str(tmp_path / "ws")
    first = provision_workspace(str(src), "run123", root)
    second = provision_workspace(str(src), "run123", root)  # no crash, same path, branch intact
    assert first == second
    branch = subprocess.run(
        ["git", "-C", second, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "agent/run123"
