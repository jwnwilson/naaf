import os
import signal
import subprocess
from pathlib import Path

from domain.agent.workspace import CommandResult


class LocalWorkspace:
    def __init__(self, root: str | Path, env: dict[str, str] | None = None):
        self._root = Path(root).resolve()
        self._env = env or {}

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
        return r.stdout + r.stderr

    def bash(self, cmd: str, timeout_s: int) -> CommandResult:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=self._root, text=True,
            env={**os.environ, **self._env},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
            return CommandResult(exit_code=proc.returncode, stdout=stdout, stderr=stderr)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()
            return CommandResult(exit_code=124, stdout="", stderr=f"timeout after {timeout_s}s")
