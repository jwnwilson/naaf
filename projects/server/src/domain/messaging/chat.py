from typing import Protocol

from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: str  # "user" or a team role (lead/backend/…)
    content: str


class ChatResponder(Protocol):
    def respond(self, role: str, history: list[ChatTurn], title: str) -> str: ...
