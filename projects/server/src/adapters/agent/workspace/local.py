import subprocess
from pathlib import Path

from domain.agent.workspace import CommandResult


class LocalWorkspace:
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        p = (self._root / path).resolve()
        if not p.is_relative_to(self._root):
            raise ValueError(f"path escapes workspace: {path}")
        return p

    def read(self, path: str) -> str:
        return self._resolve(path).read_text()

    def write(self, path: str, content: str) -> None:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def edit(self, path: str, old: str, new: str) -> None:
        p = self._resolve(path)
        text = p.read_text()
        if text.count(old) != 1:
            raise ValueError(f"expected exactly one occurrence of old text in {path}")
        p.write_text(text.replace(old, new))

    def grep(self, pattern: str, path: str | None) -> str:
        target = self._resolve(path) if path else self._root
        r = subprocess.run(["grep", "-rn", pattern, str(target)],
                           capture_output=True, text=True)
        return r.stdout

    def bash(self, cmd: str, timeout_s: int) -> CommandResult:
        try:
            r = subprocess.run(cmd, shell=True, cwd=self._root, capture_output=True,
                               text=True, timeout=timeout_s)
            return CommandResult(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(exit_code=124, stdout="", stderr=f"timeout after {timeout_s}s")
