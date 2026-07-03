from enum import StrEnum

from pydantic import Field

from domain.base import Entity


class AuthorKind(StrEnum):
    USER = "user"
    AGENT = "agent"


class MessageKind(StrEnum):
    TEXT = "text"
    FILE_WRITE = "file_write"
    QUESTION = "question"
    EVENT = "event"


class Message(Entity):
    owner_id: str
    thread_id: str  # == work_item_id
    author_kind: AuthorKind = AuthorKind.USER
    author_role: str | None = None  # lead/backend/frontend/qa/architect/devops; None for a user
    model_alias: str | None = None
    kind: MessageKind = MessageKind.TEXT
    content: str
    mentions: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    run_id: str | None = None
