# Re-export CursorState from its canonical domain location.
# This shim will be removed when interactors/dispatcher/ is deleted (Task 7).
from typing import Protocol

from domain.messaging.subscriber import CursorState as CursorState  # noqa: F401
from domain.runs.events import RunEvent
from sqlalchemy.orm import Session


class EventSubscriber(Protocol):
    name: str

    def interested_in(self, event: RunEvent) -> bool: ...

    def handle(self, event: RunEvent, session: Session) -> None: ...
