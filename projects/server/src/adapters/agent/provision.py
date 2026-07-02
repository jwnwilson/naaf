import subprocess
from pathlib import Path


def provision_workspace(repo: str, run_id: str, root: str) -> str:
    """Clone `repo` (a git URL or local path) into <root>/<run_id> and create the
    `agent/<run_id>` branch. Idempotent: if the workspace already exists, ensure the
    branch is checked out. Returns the workspace path."""
    dest = Path(root) / run_id
    branch = f"agent/{run_id}"
    if (dest / ".git").is_dir():
        _git(dest, "checkout", "-B", branch)
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", repo, str(dest)], check=True, capture_output=True, text=True)
    _git(dest, "checkout", "-B", branch)
    return str(dest)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
