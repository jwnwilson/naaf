from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from domain.runs.events import RunEvent

if TYPE_CHECKING:
    from domain.messaging.context import HandlerContext


class CursorState(BaseModel):
    last_global_seq: int = 0
    retries: int = 0


class Subscriber(Protocol):
    name: str

    def interested_in(self, message: RunEvent) -> bool: ...

    def handle(self, message: RunEvent, ctx: "HandlerContext") -> None: ...
