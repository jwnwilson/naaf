from typing import Protocol

from pydantic import BaseModel

from domain.runs.events import RunEvent


class CursorState(BaseModel):
    last_global_seq: int = 0
    retries: int = 0


class Subscriber(Protocol):
    name: str

    def interested_in(self, message: RunEvent) -> bool: ...

    def handle(self, message: RunEvent, ctx: object) -> None: ...
