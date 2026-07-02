from typing import Protocol

from pydantic import BaseModel


class CommandResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class Workspace(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def edit(self, path: str, old: str, new: str) -> None: ...
    def grep(self, pattern: str, path: str | None) -> str: ...
    def bash(self, cmd: str, timeout_s: int) -> CommandResult: ...
