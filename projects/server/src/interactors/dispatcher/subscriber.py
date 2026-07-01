from typing import Protocol

from domain.runs.events import RunEvent
from pydantic import BaseModel
from sqlalchemy.orm import Session


class CursorState(BaseModel):
    last_global_seq: int = 0
    retries: int = 0


class EventSubscriber(Protocol):
    name: str

    def interested_in(self, event: RunEvent) -> bool: ...

    def handle(self, event: RunEvent, session: Session) -> None: ...
