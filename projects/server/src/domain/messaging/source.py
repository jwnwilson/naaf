from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel


class PoisonOutcome(Enum):
    STOP = "stop"
    CONTINUE = "continue"


class Item(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    message: Any
    owner_id: str
    position: int


class MessageSource(Protocol):
    def fetch_next(self, uow) -> Item | None: ...
    def advance(self, item: Item, uow) -> None: ...
    def on_poison(self, item: Item, exc: Exception, uow_factory) -> PoisonOutcome: ...
